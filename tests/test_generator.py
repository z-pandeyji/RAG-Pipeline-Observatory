import unittest

from fastapi import HTTPException

from app.generator import _compile_prompt, _parse_model_json, _redacted_prompt_preview
from app.models import DocumentChunk


def chunk(text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id="doc:0000",
        page_start=1,
        page_end=2,
        text=text,
        token_estimate=max(1, len(text) // 4),
    )


class ParseModelJsonTests(unittest.TestCase):
    def test_parse_model_json_accepts_plain_json(self) -> None:
        parsed = _parse_model_json('{"title": "Quiz", "questions": []}')

        self.assertEqual(parsed["title"], "Quiz")
        self.assertEqual(parsed["questions"], [])

    def test_parse_model_json_accepts_markdown_fence(self) -> None:
        parsed = _parse_model_json('```json\n{"title": "Quiz", "questions": []}\n```')

        self.assertEqual(parsed["title"], "Quiz")

    def test_parse_model_json_rejects_invalid_json(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _parse_model_json("not json")

        self.assertEqual(raised.exception.status_code, 502)

    def test_parse_model_json_requires_questions_list(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _parse_model_json('{"title": "Quiz", "questions": "bad"}')

        self.assertEqual(raised.exception.status_code, 502)

    def test_redacted_prompt_preview_excludes_goal_and_context_text(self) -> None:
        secret_context = "Customer SSN 123-45-6789 appears in this document."
        secret_goal = "Generate questions about account 987654321."
        chunks = [chunk(secret_context)]

        prompt = _compile_prompt(chunks, secret_goal, question_count=5, difficulty="hard")
        preview = _redacted_prompt_preview(chunks, question_count=5, difficulty="hard")

        self.assertIn(secret_context, prompt)
        self.assertIn(secret_goal, prompt)
        self.assertNotIn(secret_context, preview)
        self.assertNotIn(secret_goal, preview)
        self.assertIn("doc:0000 pages 1-2", preview)
        self.assertIn("Context text and output schema omitted", preview)


if __name__ == "__main__":
    unittest.main()
