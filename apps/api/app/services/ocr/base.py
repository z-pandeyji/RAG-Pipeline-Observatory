from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OCRBlock:
    text: str
    region: dict | None = None


@dataclass(frozen=True)
class OCRResult:
    text: str
    width: int | None = None
    height: int | None = None
    blocks: list[OCRBlock] = field(default_factory=list)


class OCRProvider(ABC):
    provider_name: str

    async def extract_text(self, image_path: str) -> OCRResult:
        return await self._extract_text(image_path)

    @abstractmethod
    async def _extract_text(self, image_path: str) -> OCRResult:
        raise NotImplementedError
