"""Pre-retrieval: query rewriting.

Sends the user query to the LLM and asks it to reformulate the query so it
will match document chunks more precisely.  The rewritten query is used as the
embedding input instead of the raw user query.

Enabled by settings.query_rewriting_enabled (default True).
If the LLM call fails, the original query is returned unchanged.
"""

import logging

from apps.api.app.core.config import settings
from apps.api.app.services.llm.base import LLMMessage, LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a query reformulation assistant. "
    "Rewrite the user query to maximise semantic recall from a document retrieval system. "
    "Output ONLY the rewritten query — no explanation, no preamble, no punctuation changes "
    "beyond what improves retrieval."
)


class QueryRewritingService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def rewrite(self, query: str) -> str:
        """Return a retrieval-optimised rewrite of *query*, or *query* unchanged on failure."""
        if not settings.query_rewriting_enabled:
            return query
        if not query.strip():
            return query
        try:
            response = await self._llm.complete(
                LLMRequest(
                    model=settings.llm_model,
                    temperature=0.0,
                    max_tokens=256,
                    messages=[
                        LLMMessage(role="system", content=_SYSTEM_PROMPT),
                        LLMMessage(role="user", content=query),
                    ],
                )
            )
            rewritten = response.content.strip().strip('"').strip("'")
            if rewritten:
                logger.debug("[query_rewriting] '%s' -> '%s'", query[:120], rewritten[:120])
                return rewritten
        except Exception as exc:  # noqa: BLE001
            logger.warning("[query_rewriting] LLM call failed, using original query: %s", exc)
        return query
