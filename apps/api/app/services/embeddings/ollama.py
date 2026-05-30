import httpx

from apps.api.app.core.config import settings
from apps.api.app.services.embeddings.base import EmbeddingProvider, EmbeddingRequest
from apps.api.app.services.embeddings.base import EmbeddingResponse


class OllamaEmbeddingProvider(EmbeddingProvider):
    provider_name = "ollama"

    async def _embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            for text in request.texts:
                response = await client.post(
                    settings.ollama_embedding_url,
                    json={"model": request.model, "prompt": text},
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
        return EmbeddingResponse(
            vectors=vectors,
            model=request.model,
            provider=self.provider_name,
        )
