import unittest

from app.pdf_pipeline import chunk_pages


class ChunkPagesTests(unittest.TestCase):
    def test_chunk_pages_assigns_stable_chunk_ids_and_trace(self) -> None:
        chunks, trace = chunk_pages(
            "doc",
            [(1, "Alpha beta gamma."), (2, "Delta epsilon zeta.")],
            target_chars=100,
            overlap_chars=10,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "doc:0000")
        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[0].page_end, 2)
        self.assertEqual(trace.stage, "chunk")
        self.assertEqual(trace.metrics["chunks"], 1)

    def test_chunk_pages_splits_large_text_with_overlap(self) -> None:
        text = " ".join([f"Sentence {index} has enough text." for index in range(30)])

        chunks, trace = chunk_pages(
            "doc",
            [(1, text)],
            target_chars=120,
            overlap_chars=20,
        )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "doc:0000")
        self.assertEqual(chunks[1].chunk_id, "doc:0001")
        self.assertEqual(trace.metrics["chunks"], len(chunks))
        self.assertTrue(all(item.text for item in chunks))


if __name__ == "__main__":
    unittest.main()
