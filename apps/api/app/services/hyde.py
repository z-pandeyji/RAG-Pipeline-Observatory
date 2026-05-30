"""Pre-retrieval: Hypothetical Document Embeddings (HyDE).

Instead of embedding the user query directly, HyDE first asks the LLM to
generate a short *hypothetical passage* that would answer the query.  The
hypothetical passage is then embedded and used for vector search.  This
bridges the vocabulary gap between short queries and longer document chunks.

Enabled by settings.hyde_enabled (default False — query rewriting is cheaper).
Falls back to the original query on failure.
"""

import logging

from apps.api.app.core.config import settings
from apps.api.app.services.llm.base import LLMMessage, LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a document passage generator. "
    "Write a short, factual passage (2-4 sentences) that would directly answer the question. "
    "Write as if you are an expert summarising relevant source material. "
    "Output ONLY the passage — no introduction, no 'here is', no explanation."
)


class HyDEService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def hypothetical_passage(self, query: str) -> str:
        """Return a hypothetical passage for *query*, or *query* unchanged on failure."""
        if not settings.hyde_enabled:
            return query
        if not query.strip():
            return query
        try:
            response = await self._llm.complete(
                LLMRequest(
                    model=settings.llm_model,
                    temperature=0.3,
                    max_tokens=256,
                    messages=[
                        LLMMessage(role="system", content=_SYSTEM_PROMPT),
                        LLMMessage(role="user", content=query),
                    ],
                )
            )
            passage = response.content.strip()
            if passage:
                logger.debug("[hyde] generated passage (%d chars) for query '%s'", len(passage), query[:80])
                return passage
        except Exception as exc:  # noqa: BLE001
            logger.warning("[hyde] LLM call failed, using original query: %s", exc)
        return query
