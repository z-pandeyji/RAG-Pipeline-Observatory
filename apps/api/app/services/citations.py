from apps.api.app.db.models import DocumentChunk
from apps.api.app.schemas.common import CitationOut


class CitationService:
    def from_chunk(self, chunk: DocumentChunk, snippet_limit: int = 320) -> CitationOut:
        snippet = " ".join(chunk.text.split())[:snippet_limit]
        metadata = getattr(chunk, "metadata_", None) or {}
        return CitationOut(
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            page_number=chunk.page_number,
            timestamp=chunk.timestamp,
            timestamp_start=metadata.get("timestamp_start"),
            timestamp_end=metadata.get("timestamp_end"),
            url=metadata.get("youtube_url"),
            image_region=metadata.get("image_region"),
            metadata=metadata,
            source_type=chunk.source_type.value,
            text_snippet=snippet,
        )
