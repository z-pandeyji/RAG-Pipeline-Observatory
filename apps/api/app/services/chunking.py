from dataclasses import dataclass, field

from apps.api.app.services.pdf_extraction import ExtractedPage


@dataclass(frozen=True)
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    image_region: dict | None = None
    metadata: dict = field(default_factory=dict)


class SemanticChunkingService:
    def __init__(self, target_chars: int = 1400, overlap_chars: int = 180) -> None:
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk_pages(self, pages: list[ExtractedPage]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for page in pages:
            paragraphs = self._paragraphs(page.text)
            rolling = ""
            for paragraph in paragraphs:
                if len(rolling) + len(paragraph) + 1 <= self.target_chars:
                    rolling = f"{rolling}\n\n{paragraph}".strip()
                    continue
                if rolling:
                    chunks.append(self._make_chunk(rolling, len(chunks), page.page_number))
                    rolling = self._overlap(rolling)
                rolling = f"{rolling}\n\n{paragraph}".strip()
                while len(rolling) > self.target_chars * 1.35:
                    cut = self._cut_at_boundary(rolling)
                    chunks.append(
                        self._make_chunk(rolling[:cut].strip(), len(chunks), page.page_number)
                    )
                    rolling = rolling[max(0, cut - self.overlap_chars) :].strip()
            if rolling:
                chunks.append(self._make_chunk(rolling, len(chunks), page.page_number))
        return chunks

    def _paragraphs(self, text: str) -> list[str]:
        paragraphs = [item.strip() for item in text.split("\n\n") if item.strip()]
        if paragraphs:
            return paragraphs
        return [text.strip()] if text.strip() else []

    def _overlap(self, text: str) -> str:
        return text[-self.overlap_chars :].strip() if self.overlap_chars > 0 else ""

    def _cut_at_boundary(self, text: str) -> int:
        window = text[: self.target_chars]
        candidates = [
            window.rfind("\n\n"),
            window.rfind(". "),
            window.rfind("? "),
            window.rfind("! "),
        ]
        return max(max(candidates), self.target_chars // 2) + 1

    def _make_chunk(self, text: str, index: int, page_number: int) -> TextChunk:
        return TextChunk(
            text=text,
            chunk_index=index,
            page_number=page_number,
            metadata={"chunking": "semantic_paragraph_overlap"},
        )

    def chunk_text_units(self, units: list[TextChunk]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for unit in units:
            paragraphs = self._paragraphs(unit.text)
            rolling = ""
            for paragraph in paragraphs:
                if len(rolling) + len(paragraph) + 1 <= self.target_chars:
                    rolling = f"{rolling}\n\n{paragraph}".strip()
                    continue
                if rolling:
                    chunks.append(self._copy_chunk(unit, rolling, len(chunks)))
                    rolling = self._overlap(rolling)
                rolling = f"{rolling}\n\n{paragraph}".strip()
            if rolling:
                chunks.append(self._copy_chunk(unit, rolling, len(chunks)))
        return chunks

    def _copy_chunk(self, source: TextChunk, text: str, index: int) -> TextChunk:
        return TextChunk(
            text=text,
            chunk_index=index,
            page_number=source.page_number,
            timestamp_start=source.timestamp_start,
            timestamp_end=source.timestamp_end,
            image_region=source.image_region,
            metadata={**source.metadata, "chunking": "semantic_source_unit_overlap"},
        )
