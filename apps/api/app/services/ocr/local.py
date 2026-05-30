from apps.api.app.services.ocr.base import OCRProvider, OCRResult


class PlaceholderOCRProvider(OCRProvider):
    provider_name = "placeholder"

    async def _extract_text(self, image_path: str) -> OCRResult:
        raise ValueError("No local OCR provider configured.")
