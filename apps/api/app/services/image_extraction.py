import struct
from dataclasses import dataclass
from pathlib import Path

from apps.api.app.services.ocr.base import OCRProvider, OCRResult
from apps.api.app.services.ocr.local import PlaceholderOCRProvider


SAFE_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class ImageSource:
    filename: str
    width: int | None
    height: int | None
    ocr: OCRResult


class ImageValidationService:
    def validate(self, filename: str, content_type: str | None, content: bytes) -> str:
        suffix = Path(filename).suffix.lower().lstrip(".")
        normalized = "jpg" if suffix == "jpeg" else suffix
        content_extension = SAFE_IMAGE_TYPES.get(content_type or "")
        if normalized not in {"png", "jpg", "webp"} or content_extension is None:
            raise ValueError("Only png, jpg/jpeg, and webp images are supported.")
        if not self._magic_matches(content_extension, content):
            raise ValueError("Image bytes do not match the declared safe type.")
        return content_extension

    def dimensions(self, extension: str, content: bytes) -> tuple[int | None, int | None]:
        if extension == "png" and len(content) >= 24:
            return struct.unpack(">II", content[16:24])
        return None, None

    def _magic_matches(self, extension: str, content: bytes) -> bool:
        if extension == "png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if extension == "jpg":
            return content.startswith(b"\xff\xd8\xff")
        if extension == "webp":
            return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        return False


class ImageExtractionService:
    def __init__(self, ocr_provider: OCRProvider | None = None) -> None:
        self.ocr_provider = ocr_provider or PlaceholderOCRProvider()

    async def extract(
        self,
        image_path: str,
        filename: str,
        width: int | None,
        height: int | None,
    ) -> ImageSource:
        ocr = await self.ocr_provider.extract_text(image_path)
        return ImageSource(
            filename=filename,
            width=ocr.width or width,
            height=ocr.height or height,
            ocr=ocr,
        )
