from apps.api.app.core.config import settings
from apps.api.app.services.reranking.base import Reranker
from apps.api.app.services.reranking.score_filter import ScoreFilterReranker
from apps.api.app.services.reranking.vector_order import VectorOrderReranker


def get_reranker() -> Reranker:
    if settings.reranker_provider == "vector_order":
        return VectorOrderReranker()
    # Default: score_filter (filters low-score chunks + deduplicates)
    return ScoreFilterReranker()
