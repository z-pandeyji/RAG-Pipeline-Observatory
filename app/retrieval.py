import re
from collections import Counter

from app.models import DocumentChunk, PipelineTrace


class LocalBm25Index:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks

    def search(self, query: str, top_k: int = 5) -> tuple[list[DocumentChunk], PipelineTrace]:
        query_terms = _terms(query)
        scored = []
        for chunk in self.chunks:
            counts = Counter(_terms(chunk.text))
            score = sum(counts[term] for term in query_terms)
            if score > 0:
                scored.append((score, chunk))
        if scored:
            ranked = [chunk for _, chunk in sorted(scored, key=lambda item: item[0], reverse=True)]
        else:
            ranked = self.chunks
        returned = ranked[:top_k]
        return returned, PipelineTrace(stage="retrieve", metrics={"returned": len(returned)})


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
