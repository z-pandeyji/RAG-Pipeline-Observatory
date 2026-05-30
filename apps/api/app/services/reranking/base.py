from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RerankCandidate:
    chunk_id: UUID
    score: float
    text: str


class Reranker(ABC):
    provider_name: str

    async def rerank(self, query: str, candidates: list[RerankCandidate]) -> list[RerankCandidate]:
        return await self._rerank(query, candidates)

    @abstractmethod
    async def _rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankCandidate]:
        raise NotImplementedError
