from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingRequest:
    texts: list[str]
    model: str


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    model: str
    provider: str


class EmbeddingProvider(ABC):
    provider_name: str

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return await self._embed(request)

    @abstractmethod
    async def _embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError
