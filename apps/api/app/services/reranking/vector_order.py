from apps.api.app.services.reranking.base import RerankCandidate, Reranker


class VectorOrderReranker(Reranker):
    provider_name = "vector_order"

    async def _rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankCandidate]:
        return candidates
