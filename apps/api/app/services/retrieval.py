import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import settings
from apps.api.app.repositories.retrieval import RetrievalRepository
from apps.api.app.schemas.retrieval import RetrievedChunkOut
from apps.api.app.services.bm25_index import BM25Index
from apps.api.app.services.citations import CitationService
from apps.api.app.services.embeddings.base import EmbeddingProvider, EmbeddingRequest
from apps.api.app.services.embeddings.factory import get_embedding_provider
from apps.api.app.services.hyde import HyDEService
from apps.api.app.services.llm.factory import get_llm_provider
from apps.api.app.services.qdrant import QdrantService
from apps.api.app.services.query_rewriting import QueryRewritingService
from apps.api.app.services.reranking.base import RerankCandidate, Reranker
from apps.api.app.services.reranking.factory import get_reranker
from apps.api.app.services.tool_runs import ToolRunLogger

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
        qdrant: QdrantService | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.repository = RetrievalRepository(session)
        self.citations = CitationService()
        self.tool_runs = ToolRunLogger(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.qdrant = qdrant or QdrantService()
        self.reranker = reranker or get_reranker()
        _llm = get_llm_provider()
        self._query_rewriter = QueryRewritingService(_llm)
        self._hyde = HyDEService(_llm)

    async def retrieve(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query: str,
        document_ids: list[UUID],
        limit: int,
        source_type: str | None = None,
    ) -> tuple[list[RetrievedChunkOut], UUID]:
        # ── Pre-retrieval: query transformation ──────────────────────────────
        embedding_query = query
        if settings.hyde_enabled:
            embedding_query = await self._hyde.hypothetical_passage(query)
        elif settings.query_rewriting_enabled:
            embedding_query = await self._query_rewriter.rewrite(query)

        embedding_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "query_embedding",
            {
                "query": query,
                "embedding_query": embedding_query,
                "document_ids": [str(item) for item in document_ids],
                "limit": limit,
                "source_type": source_type,
                "query_rewriting": settings.query_rewriting_enabled,
                "hyde": settings.hyde_enabled,
            },
        )
        try:
            embedding_response = await self.embedding_provider.embed(
                EmbeddingRequest(texts=[embedding_query], model=settings.embedding_model)
            )
            query_vector = embedding_response.vectors[0] if embedding_response.vectors else []
        except Exception as exc:
            await self.tool_runs.finish_failure(embedding_run, str(exc))
            raise
        else:
            await self.tool_runs.finish_success(
                embedding_run,
                {
                    "provider": embedding_response.provider,
                    "vectors": len(embedding_response.vectors),
                },
            )

        # ── Vector retrieval ────────────────────────────────────────────────
        # Retrieve more candidates when hybrid search is enabled so BM25 can
        # reorder them; clip to *limit* after fusion.
        vector_limit = limit * 2 if settings.hybrid_search_enabled else limit
        vector_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "vector_retrieval",
            {"document_ids": [str(item) for item in document_ids], "limit": vector_limit},
        )
        try:
            qdrant_results = await self.qdrant.search(
                vector=query_vector,
                workspace_id=workspace_id,
                user_id=user_id,
                document_ids=document_ids,
                limit=vector_limit,
                source_type=source_type,
            )
            scored_ids = self.qdrant.parse_search_results(qdrant_results)
        except Exception as exc:
            await self.tool_runs.finish_failure(vector_run, str(exc))
            raise
        else:
            await self.tool_runs.finish_success(vector_run, {"returned": len(scored_ids)})

        # ── Chunk hydration ─────────────────────────────────────────────────
        hydration_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "chunk_hydration",
            {"chunk_ids": [str(chunk_id) for chunk_id, _ in scored_ids]},
        )
        try:
            score_by_id = {chunk_id: score for chunk_id, score in scored_ids}
            chunks = await self.repository.hydrate_chunks_by_ids(
                [chunk_id for chunk_id, _ in scored_ids],
                workspace_id,
                user_id,
            )
        except Exception as exc:
            await self.tool_runs.finish_failure(hydration_run, str(exc))
            raise
        else:
            await self.tool_runs.finish_success(hydration_run, {"hydrated": len(chunks)})

        # ── Hybrid BM25 + vector fusion ──────────────────────────────────────
        if settings.hybrid_search_enabled and chunks:
            texts = [chunk.text for chunk in chunks]
            bm25_index = BM25Index(texts)
            bm25_scores = bm25_index.score(query)  # use original query for lexical matching
            vector_scores = [score_by_id.get(chunk.id, 0.0) for chunk in chunks]
            fused = BM25Index.rrf_fuse(bm25_scores, vector_scores)
            # Sort by fused score — keep original vector cosine scores in score_by_id
            # (RRF scores are ~0.016–0.033, too small for the cosine similarity threshold)
            paired = sorted(zip(fused, chunks), key=lambda pair: pair[0], reverse=True)
            chunks = [chunk for _, chunk in paired]
            # score_by_id is intentionally NOT updated with RRF scores so that
            # ScoreFilterReranker's threshold applies to cosine similarity, not RRF values
            logger.debug("[hybrid_search] fused %d candidates (BM25 + vector RRF)", len(chunks))

        # Clip to requested limit after hybrid fusion
        chunks = chunks[:limit]

        # ── Post-retrieval: reranking ────────────────────────────────────────
        rerank_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "reranking",
            {"candidate_count": len(chunks), "provider": self.reranker.provider_name},
        )
        try:
            reranked = await self.reranker.rerank(
                query,
                [
                    RerankCandidate(
                        chunk_id=chunk.id,
                        score=score_by_id.get(chunk.id, 0.0),
                        text=chunk.text,
                    )
                    for chunk in chunks
                ],
            )
        except Exception as exc:
            await self.tool_runs.finish_failure(rerank_run, str(exc))
            raise
        reranked_ids = [candidate.chunk_id for candidate in reranked]
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        ordered_chunks = [
            chunk_by_id[chunk_id] for chunk_id in reranked_ids if chunk_id in chunk_by_id
        ]
        retrieved = [
            RetrievedChunkOut(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                score=score_by_id.get(chunk.id, 0.0),
                text=chunk.text,
                citation=self.citations.from_chunk(chunk),
            )
            for chunk in ordered_chunks
        ]
        await self.tool_runs.finish_success(rerank_run, {"returned": len(retrieved)})
        return retrieved, rerank_run.id
