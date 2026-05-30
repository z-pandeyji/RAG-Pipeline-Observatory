import unittest
from uuid import uuid4

from apps.api.app.schemas.quizzes import QuizOut
from apps.api.app.services.llm.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from apps.api.app.services.qdrant import QdrantService


class FakeProvider(LLMProvider):
    provider_name = "fake"

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="ok", model=request.model, provider=self.provider_name)


class BackendFoundationTests(unittest.TestCase):
    def test_qdrant_filter_always_scopes_workspace_and_user(self) -> None:
        workspace_id = uuid4()
        user_id = uuid4()
        document_id = uuid4()

        scoped_filter = QdrantService().scope_filter(workspace_id, user_id, [document_id])

        self.assertIn(
            {"key": "workspace_id", "match": {"value": str(workspace_id)}},
            scoped_filter["must"],
        )
        self.assertIn(
            {"key": "user_id", "match": {"value": str(user_id)}},
            scoped_filter["must"],
        )
        self.assertIn(
            {"key": "document_id", "match": {"any": [str(document_id)]}},
            scoped_filter["must"],
        )

    def test_llm_provider_calls_through_base_abstraction(self) -> None:
        provider = FakeProvider()
        request = LLMRequest(model="gemma", messages=[LLMMessage(role="user", content="hello")])

        response = self.run_async(provider.complete(request))

        self.assertEqual(response.content, "ok")
        self.assertEqual(response.provider, "fake")

    def test_quiz_create_response_does_not_expose_answer_key(self) -> None:
        quiz = QuizOut(
            quiz_id=uuid4(),
            title="Quiz",
            questions=[{"question_id": "q1", "question": "What is cited?", "type": "mcq"}],
            tool_run_id=uuid4(),
        )

        serialized = quiz.model_dump()

        self.assertNotIn("answer_key", serialized)

    def run_async(self, awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
