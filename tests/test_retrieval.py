import unittest

from app.models import DocumentChunk
from app.retrieval import LocalBm25Index


def chunk(chunk_id: str, text: str, page: int = 1) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        page_start=page,
        page_end=page,
        text=text,
        token_estimate=max(1, len(text) // 4),
    )


class LocalBm25IndexTests(unittest.TestCase):
    def test_search_ranks_matching_chunk_first(self) -> None:
        index = LocalBm25Index(
            [
                chunk("doc:0000", "Photosynthesis converts light energy into chemical energy."),
                chunk("doc:0001", "The French Revolution reshaped European politics."),
            ]
        )

        retrieved, trace = index.search("light energy photosynthesis", top_k=2)

        self.assertEqual(retrieved[0].chunk_id, "doc:0000")
        self.assertEqual(trace.stage, "retrieve")
        self.assertEqual(trace.metrics["returned"], 1)

    def test_unmatched_query_returns_bounded_fallback(self) -> None:
        index = LocalBm25Index(
            [
                chunk("doc:0000", "Algebraic expressions and equations."),
                chunk("doc:0001", "Cell membranes regulate transport."),
                chunk("doc:0002", "Economic inflation changes purchasing power."),
            ]
        )

        retrieved, trace = index.search("volcano basalt magma", top_k=2)

        self.assertEqual([item.chunk_id for item in retrieved], ["doc:0000", "doc:0001"])
        self.assertEqual(len(retrieved), 2)
        self.assertEqual(trace.metrics["returned"], 2)


if __name__ == "__main__":
    unittest.main()
