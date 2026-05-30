import httpx

from apps.api.app.core.config import settings
from apps.api.app.services.embeddings.base import EmbeddingProvider, EmbeddingRequest
from apps.api.app.services.embeddings.base import EmbeddingResponse


class LMStudioEmbeddingProvider(EmbeddingProvider):
    provider_name = "lmstudio"

    async def _embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        payload = {"model": request.model, "input": request.texts}
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            response = await client.post(settings.lmstudio_embedding_url, json=payload)
            response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return EmbeddingResponse(
            vectors=[item["embedding"] for item in data],
            model=request.model,
            provider=self.provider_name,
        )
