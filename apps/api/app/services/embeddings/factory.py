from apps.api.app.core.config import settings
from apps.api.app.services.embeddings.base import EmbeddingProvider
from apps.api.app.services.embeddings.lmstudio import LMStudioEmbeddingProvider
from apps.api.app.services.embeddings.ollama import OllamaEmbeddingProvider


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "lmstudio":
        return LMStudioEmbeddingProvider()
    return OllamaEmbeddingProvider()
