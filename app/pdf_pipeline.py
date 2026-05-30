import re

from app.models import DocumentChunk, PipelineTrace


def chunk_pages(
    document_id: str,
    pages: list[tuple[int, str]],
    target_chars: int = 1400,
    overlap_chars: int = 180,
) -> tuple[list[DocumentChunk], PipelineTrace]:
    joined = "\n".join(text for _, text in pages)
    page_start = pages[0][0] if pages else 1
    page_end = pages[-1][0] if pages else page_start
    parts = _split_text(joined, target_chars, overlap_chars)
    chunks = [
        DocumentChunk(
            chunk_id=f"{document_id}:{index:04d}",
            page_start=page_start,
            page_end=page_end,
            text=part,
            token_estimate=max(1, len(part) // 4),
        )
        for index, part in enumerate(parts)
    ]
    return chunks, PipelineTrace(stage="chunk", metrics={"chunks": len(chunks)})


def _split_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    if len(normalized) <= target_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + target_chars)
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(end - overlap_chars, start + 1)
    return [chunk for chunk in chunks if chunk]
