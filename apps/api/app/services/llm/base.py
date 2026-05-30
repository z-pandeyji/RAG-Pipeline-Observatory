from abc import ABC, abstractmethod
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    temperature: float = 0.2
    max_tokens: int = 1600
    structured_json: bool = False


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    provider: str


class LLMProvider(ABC):
    provider_name: str

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._complete(request)

    async def generate_json(self, request: LLMRequest, schema_name: str | None = None) -> LLMResponse:
        return await self._complete(replace(request, structured_json=True))

    @abstractmethod
    async def _complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
