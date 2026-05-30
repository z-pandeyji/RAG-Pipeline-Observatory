from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


class PdfExtractionService:
    def extract_pages(self, pdf_path: str) -> list[ExtractedPage]:
        pages: list[ExtractedPage] = []
        with fitz.open(Path(pdf_path)) as document:
            for page_index, page in enumerate(document, start=1):
                normalized = self._normalize_page_text(page.get_text("text"))
                if normalized:
                    pages.append(ExtractedPage(page_number=page_index, text=normalized))
        if not pages:
            raise ValueError("No selectable text found in PDF.")
        return pages

    def _normalize_page_text(self, text: str) -> str:
        paragraphs: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            stripped = " ".join(line.split())
            if stripped:
                current.append(stripped)
                continue
            if current:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))
        return "\n\n".join(paragraphs)
