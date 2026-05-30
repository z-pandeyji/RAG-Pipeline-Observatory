"""Post-retrieval: score-based filter + deduplication reranker.

Replaces the pass-through VectorOrderReranker with a reranker that:
  1. Filters chunks below a configurable cosine similarity threshold.
  2. Deduplicates near-identical chunks by Jaccard similarity on word sets.
  3. Returns remaining chunks ordered by descending score.

Config keys (apps.api.app.core.config):
  rerank_min_score: float = 0.15
  rerank_dedup_threshold: float = 0.85
"""

import logging
import re

from apps.api.app.core.config import settings
from apps.api.app.services.reranking.base import RerankCandidate, Reranker

logger = logging.getLogger(__name__)


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


class ScoreFilterReranker(Reranker):
    provider_name = "score_filter"

    async def _rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankCandidate]:
        # 1. Filter below minimum score
        passed = [c for c in candidates if c.score >= settings.rerank_min_score]
        if not passed and candidates:
            # Fallback: keep top candidate even if below threshold
            passed = [max(candidates, key=lambda c: c.score)]
            logger.debug(
                "[score_filter] all %d candidates below threshold %.2f; keeping top 1",
                len(candidates),
                settings.rerank_min_score,
            )

        # 2. Deduplicate by Jaccard similarity on word sets
        deduped: list[RerankCandidate] = []
        seen_tokens: list[set[str]] = []
        for candidate in sorted(passed, key=lambda c: c.score, reverse=True):
            tokens = _tokenise(candidate.text)
            is_dup = any(
                _jaccard(tokens, seen) >= settings.rerank_dedup_threshold
                for seen in seen_tokens
            )
            if not is_dup:
                deduped.append(candidate)
                seen_tokens.append(tokens)

        logger.debug(
            "[score_filter] %d -> %d after filter (min_score=%.2f), %d after dedup",
            len(candidates),
            len(passed),
            settings.rerank_min_score,
            len(deduped),
        )
        return deduped
