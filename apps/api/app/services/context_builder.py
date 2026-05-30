from dataclasses import dataclass

from apps.api.app.core.config import settings
from apps.api.app.schemas.retrieval import RetrievedChunkOut


@dataclass(frozen=True)
class ContextPackage:
    text: str
    chunks: list[RetrievedChunkOut]


class ContextBuilderService:
    def __init__(self, max_chars: int = settings.max_context_chars) -> None:
        self.max_chars = max_chars

    def build(self, chunks: list[RetrievedChunkOut]) -> ContextPackage:
        seen: set[str] = set()
        selected: list[RetrievedChunkOut] = []
        parts: list[str] = []
        used = 0
        for chunk in chunks:
            chunk_key = str(chunk.chunk_id)
            if chunk_key in seen:
                continue
            block = (
                "<UNTRUSTED_RETRIEVED_CONTENT>\n"
                f"chunk_id: {chunk.chunk_id}\n"
                f"document_id: {chunk.document_id}\n"
                f"page_number: {chunk.citation.page_number}\n"
                f"source_type: {chunk.citation.source_type}\n"
                f"text:\n{chunk.text}\n"
                "</UNTRUSTED_RETRIEVED_CONTENT>"
            )
            if parts and used + len(block) + 2 > self.max_chars:
                break
            if not parts and len(block) > self.max_chars:
                block = block[: self.max_chars]
            parts.append(block)
            selected.append(chunk)
            seen.add(chunk_key)
            used += len(block) + 2
        return ContextPackage(text="\n\n".join(parts), chunks=selected)
