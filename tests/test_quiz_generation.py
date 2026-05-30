import asyncio
import json
import unittest
from types import SimpleNamespace
from uuid import uuid4

from apps.api.app.core.config import settings
from apps.api.app.db.models import QuizGenerationJobStatus
from apps.api.app.schemas.common import CitationOut
from apps.api.app.schemas.retrieval import RetrievedChunkOut
from apps.api.app.services.llm.base import LLMProvider, LLMRequest, LLMResponse
from apps.api.app.services.quiz_json_utils import extract_json_candidate
from apps.api.app.services.quizzes import QuizService


class FakeRetrieval:
    def __init__(self, chunks: list[RetrievedChunkOut]) -> None:
        self.chunks = chunks
        self.calls = []

    async def retrieve(self, workspace_id, user_id, query, document_ids, limit, source_type=None):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "query": query,
                "document_ids": document_ids,
            }
        )
        return self.chunks, uuid4()


class FakeLLM(LLMProvider):
    provider_name = "fake"

    def __init__(self, content: str | list[str]) -> None:
        self.content = [content] if isinstance(content, str) else list(content)
        self.requests: list[LLMRequest] = []

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        content = self.content.pop(0) if self.content else ""
        return LLMResponse(content=content, model=request.model, provider=self.provider_name)


class FakeToolRuns:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.failures: list[str] = []

    async def start(self, workspace_id, user_id, tool_name, input_):
        self.started.append(tool_name)
        return SimpleNamespace(id=uuid4(), tool_name=tool_name)

    async def finish_success(self, run, output):
        run.output = output
        return run

    async def finish_failure(self, run, error):
        run.error = error
        self.failures.append(error)
        return run


class FakeQuizRepository:
    def __init__(self) -> None:
        self.created = None
        self.attempts = []
        self.quiz = None
        self.jobs = []
        self.job_updates = []

    async def create(self, **kwargs):
        self.created = kwargs
        self.quiz = SimpleNamespace(id=uuid4(), **kwargs)
        return self.quiz

    async def get_scoped(self, quiz_id, workspace_id, user_id):
        return self.quiz

    async def list_scoped(self, workspace_id, user_id):
        return [self.quiz] if self.quiz else []

    async def create_attempt(self, quiz, submitted_answers, score):
        attempt = SimpleNamespace(id=uuid4(), submitted_answers=submitted_answers, score=score)
        self.attempts.append(attempt)
        return attempt

    async def create_generation_job(
        self,
        workspace_id,
        user_id,
        document_id,
        query,
        difficulty,
        quiz_type,
        requested_question_count,
    ):
        job = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            document_id=document_id,
            query=query,
            difficulty=difficulty,
            quiz_type=quiz_type,
            requested_question_count=requested_question_count,
            status=QuizGenerationJobStatus.queued,
            error_code=None,
            error_message=None,
            suggestion=None,
            selected_chunk_ids=[],
            source_pack=[],
            prompt_text=None,
            raw_llm_response=None,
            extracted_json=None,
            repaired_llm_response=None,
            validation_errors=[],
            fallback_used=False,
            warnings=[],
            timings={},
            created_quiz_id=None,
            warning=None,
            created_at=None,
            updated_at=None,
            completed_at=None,
        )
        self.jobs.append(job)
        return job

    async def update_job(self, job, **values):
        for key, value in values.items():
            setattr(job, key, value)
        self.job_updates.append(dict(values))
        return job

    async def get_job_scoped(self, job_id, workspace_id, user_id):
        return next((job for job in self.jobs if job.id == job_id), None)

    async def list_jobs_scoped(self, workspace_id, user_id):
        return list(self.jobs)


class FakeCitationRepository:
    def __init__(self) -> None:
        self.saved = []

    async def create_many(self, workspace_id, user_id, citations):
        self.saved.extend(citations)
        return []


def retrieved_chunk() -> RetrievedChunkOut:
    document_id = uuid4()
    chunk_id = uuid4()
    citation = CitationOut(
        document_id=document_id,
        chunk_id=chunk_id,
        page_number=2,
        source_type="pdf",
        text_snippet="The mitochondria produces cellular energy.",
    )
    return RetrievedChunkOut(
        document_id=document_id,
        chunk_id=chunk_id,
        score=0.9,
        text="The mitochondria produces cellular energy.",
        citation=citation,
    )


def quiz_json(
    source_index: int = 0,
    correct_option_index: int | str | None = 0,
    *,
    correct_answer: str | None = None,
    options: list[str] | None = None,
    question_type: str = "mcq",
) -> str:
    question = {
        "question_id": "q1",
        "question": "What produces cellular energy?",
        "type": question_type,
        "options": options if options is not None else ["A", "B", "C", "D"],
        "explanation": "The cited chunk says mitochondria produces energy.",
        "source_indices": [source_index],
    }
    if question_type == "mcq":
        if correct_option_index is not None:
            question["correct_option_index"] = correct_option_index
        if correct_answer is not None:
            question["correct_answer"] = correct_answer
    else:
        question["options"] = options if options is not None else []
        question["correct_answer"] = correct_answer or "mitochondria"
    return json.dumps(
        {
            "title": "Cell Biology Quiz",
            "questions": [question],
        }
    )


def duplicate_questions_json() -> str:
    question = json.loads(quiz_json())["questions"][0]
    duplicate = dict(question)
    duplicate["question_id"] = "q2"
    return json.dumps({"title": "Duplicate Quiz", "questions": [question, duplicate]})


class QuizGenerationTests(unittest.TestCase):
    def build_service(self, llm_content: str | list[str], chunks: list[RetrievedChunkOut]):
        service = QuizService(
            session=None,
            llm_provider=FakeLLM(llm_content),
            retrieval=FakeRetrieval(chunks),
        )
        service.tool_runs = FakeToolRuns()
        service.repository = FakeQuizRepository()
        service.citations = FakeCitationRepository()
        return service

    def test_quiz_generation_uses_retrieval_scope_and_document_filter(self) -> None:
        chunk = retrieved_chunk()
        workspace_id = uuid4()
        user_id = uuid4()
        document_id = chunk.document_id
        service = self.build_service(quiz_json(), [chunk])

        asyncio.run(
            service.generate_from_document_or_query(
                workspace_id,
                user_id,
                document_id,
                None,
                1,
                "medium",
                "mcq",
            )
        )

        call = service.retrieval.calls[0]
        self.assertEqual(call["workspace_id"], workspace_id)
        self.assertEqual(call["user_id"], user_id)
        self.assertEqual(call["document_ids"], [document_id])

    def test_quiz_create_get_list_responses_do_not_expose_answers(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])
        response = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )
        get_response = asyncio.run(service.get_quiz(response.quiz_id, uuid4(), uuid4()))
        list_response = asyncio.run(service.list_quizzes(uuid4(), uuid4()))[0]

        payloads = [
            response.model_dump(mode="json"),
            get_response.model_dump(mode="json"),
            list_response.model_dump(mode="json"),
        ]
        for payload in payloads:
            text = json.dumps(payload)
            self.assertNotIn("answer_key", text)
            self.assertNotIn("correct_answer", text)
            self.assertNotIn("explanation", text)
            self.assertTrue(payload["questions"][0]["answer_hidden"])

    def test_quiz_attempt_reveals_answer_only_after_submission_and_is_stored(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])
        quiz = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        attempt = asyncio.run(service.submit_attempt(quiz.quiz_id, uuid4(), uuid4(), "q1", "A"))

        self.assertTrue(attempt.is_correct)
        self.assertEqual(attempt.correct_answer, "A")
        self.assertIn("mitochondria", attempt.explanation)
        self.assertEqual(len(attempt.citations), 1)
        self.assertEqual(len(service.repository.attempts), 1)

    def test_mcq_correct_option_index_maps_to_correct_answer(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            quiz_json(options=["A. Red", "B. Blue", "C. Green"], correct_option_index=1),
            [chunk],
        )

        asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        answer = service.repository.created["answer_key"]["q1"]
        self.assertEqual(answer["correct_answer"], "Blue")

    def test_invalid_correct_option_index_uses_fallback_when_enabled(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(correct_option_index=99), [chunk])

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        self.assertIn("fallback", response.job.warning)

    def test_invalid_source_index_is_rejected(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(source_index=99), [chunk])

        with self.assertRaisesRegex(ValueError, "invalid source indexes"):
            asyncio.run(
                service.generate_from_document_or_query(
                    uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
                )
            )

    def test_llm_cannot_invent_chunk_ids_anymore(self) -> None:
        chunk = retrieved_chunk()
        invented_chunk_id_payload = json.dumps(
            {
                "title": "Bad Quiz",
                "questions": [
                    {
                        "question_id": "q1",
                        "question": "What produces cellular energy?",
                        "type": "mcq",
                        "options": ["A", "B", "C", "D"],
                        "correct_option_index": 0,
                        "explanation": "The cited chunk says mitochondria produces energy.",
                        "citation_chunk_ids": [str(uuid4())],
                    }
                ],
            }
        )
        service = self.build_service(invented_chunk_id_payload, [chunk])

        with self.assertRaisesRegex(ValueError, "invalid source indexes"):
            asyncio.run(
                service.generate_from_document_or_query(
                    uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
                )
            )

    def test_llm_output_accepts_fenced_json(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(f"```json\n{quiz_json()}\n```", [chunk])

        result = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertEqual(result.title, "Cell Biology Quiz")
        self.assertEqual(len(result.questions), 1)

    def test_raw_json_parses(self) -> None:
        service = self.build_service(quiz_json(), [])

        payload = service._parse_quiz_json(quiz_json())

        self.assertIsNotNone(payload)
        self.assertEqual(payload["title"], "Cell Biology Quiz")

    def test_text_around_json_parses(self) -> None:
        service = self.build_service(quiz_json(), [])

        payload = service._parse_quiz_json(f"Here is the quiz:\n{quiz_json()}\nDone.")

        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["questions"]), 1)

    def test_smart_quotes_and_trailing_commas_parse(self) -> None:
        candidate = extract_json_candidate(
            "Here:\n"
            "\u201cquestions\u201d: []"
        )

        self.assertEqual(candidate, '{"questions": []}')

    def test_trailing_commas_are_repaired(self) -> None:
        candidate = extract_json_candidate('{"questions":[{"question":"x",}],}')

        self.assertIn('"questions"', candidate)

    def test_text_with_non_json_brackets_before_json_parses(self) -> None:
        service = self.build_service(quiz_json(), [])

        payload = service._parse_quiz_json(f"Notes [not json] before payload:\n{quiz_json()}")

        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["questions"]), 1)

    def test_array_response_wraps_into_questions_object(self) -> None:
        service = self.build_service(quiz_json(), [])
        question = json.loads(quiz_json())["questions"][0]

        payload = service._parse_quiz_json(json.dumps([question]))

        self.assertIsNotNone(payload)
        self.assertEqual(payload["title"], "Generated Quiz")
        self.assertEqual(len(payload["questions"]), 1)

    def test_llm_output_malformed_json_uses_deterministic_fallback(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service("not json at all", [chunk])

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        self.assertEqual(response.job.status, "succeeded")
        self.assertIn("deterministic fallback", response.job.warning)
        self.assertEqual(len(service.llm_provider.requests), 2)

    def test_llm_output_repairs_invalid_json_once(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            [
                "title: Cell Biology Quiz, questions: []",
                quiz_json(),
            ],
            [chunk],
        )

        result = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertEqual(result.title, "Cell Biology Quiz")
        self.assertEqual(len(service.llm_provider.requests), 2)

    def test_llm_output_normalizes_wrapped_payload_keys(self) -> None:
        chunk = retrieved_chunk()
        wrapped_payload = json.dumps(
            {
                "data": {
                    "quiz_title": "Wrapped Quiz",
                    "quiz_questions": json.loads(quiz_json())["questions"],
                }
            }
        )
        service = self.build_service(wrapped_payload, [chunk])

        result = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertEqual(result.title, "Wrapped Quiz")
        self.assertEqual(len(result.questions), 1)

    def test_public_response_does_not_expose_correct_option_index(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(correct_option_index=1), [chunk])

        response = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        text = json.dumps(response.model_dump(mode="json"))
        self.assertNotIn("correct_option_index", text)
        self.assertNotIn("correct_answer", text)

    def test_legacy_correct_answer_repairs_when_it_matches_one_option(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            quiz_json(
                correct_option_index=None,
                correct_answer="Blue",
                options=["A. Red", "B. Blue", "C. Green"],
            ),
            [chunk],
        )

        asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        answer = service.repository.created["answer_key"]["q1"]
        self.assertEqual(answer["correct_answer"], "Blue")

    def test_legacy_correct_answer_falls_back_when_ambiguous(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            quiz_json(
                correct_option_index=None,
                correct_answer="Blue",
                options=["A. Blue", "B. Blue"],
            ),
            [chunk],
        )

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        self.assertIn("fallback", response.job.warning)

    def test_duplicate_mcq_options_are_repaired_without_422(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            quiz_json(
                options=["A. Mitochondria", "B. Mitochondria", "C. Ribosome"],
                correct_option_index=0,
            ),
            [chunk],
        )

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        public_options = response.quiz.questions[0].options
        normalized = [service._normalize_option_text(option) for option in public_options]
        self.assertEqual(len(normalized), len(set(normalized)))
        self.assertGreaterEqual(len(public_options), 2)

    def test_short_answer_still_uses_correct_answer(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(
            quiz_json(question_type="short_answer", correct_answer="mitochondria"),
            [chunk],
        )

        asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "short_answer"
            )
        )

        answer = service.repository.created["answer_key"]["q1"]
        self.assertEqual(answer["correct_answer"], "mitochondria")

    def test_tool_runs_logged_for_generation_and_attempt(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])
        quiz = asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )
        asyncio.run(service.submit_attempt(quiz.quiz_id, uuid4(), uuid4(), "q1", "B"))

        for tool_name in [
            "quiz_retrieval",
            "quiz_context_building",
            "quiz_generation",
            "quiz_validation",
            "quiz_persistence",
            "quiz_attempt_grading",
        ]:
            self.assertIn(tool_name, service.tool_runs.started)

    def test_source_indices_are_mapped_to_real_chunk_ids(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])

        asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
            )
        )

        answer = service.repository.created["answer_key"]["q1"]
        self.assertEqual(answer["citations"][0]["chunk_id"], str(chunk.chunk_id))

    def test_quiz_generation_uses_limited_numbered_context(self) -> None:
        chunks = [retrieved_chunk() for _ in range(7)]
        service = self.build_service(quiz_json(), chunks)

        asyncio.run(
            service.generate_from_document_or_query(
                uuid4(), uuid4(), None, "cell energy", 1, "easy", "mcq"
            )
        )

        request = service.llm_provider.requests[0]
        prompt = request.messages[-1].content
        self.assertIn("SOURCE 0", prompt)
        self.assertIn("source_indices", prompt)
        self.assertNotIn("citation_chunk_ids", prompt)
        self.assertNotIn("SOURCE 5", prompt)
        self.assertLessEqual(len(prompt), 6500)

    def test_generate_with_job_persists_source_pack_before_llm_call(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "medium", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        job = service.repository.jobs[0]
        self.assertEqual(job.status, QuizGenerationJobStatus.succeeded)
        self.assertEqual(job.selected_chunk_ids, [str(chunk.chunk_id)])
        self.assertEqual(job.source_pack[0]["chunk_id"], str(chunk.chunk_id))
        self.assertEqual(job.source_pack[0]["source_index"], 0)
        self.assertEqual(job.created_quiz_id, service.repository.quiz.id)
        self.assertIsNotNone(job.raw_llm_response)
        self.assertIsNotNone(job.extracted_json)

    def test_normal_quiz_response_does_not_expose_debug_or_answers(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "medium", "mcq"
            )
        )

        text = json.dumps(response.model_dump(mode="json"))
        self.assertNotIn("prompt_text", text)
        self.assertNotIn("raw_llm_response", text)
        self.assertNotIn("answer_key", text)
        self.assertNotIn("correct_answer", text)
        self.assertNotIn("correct_option_index", text)

    def test_job_out_does_not_lazy_load_expired_updated_at(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])

        class ExpiredJob:
            def __init__(self):
                self.id = uuid4()
                self.workspace_id = uuid4()
                self.user_id = uuid4()
                self.document_id = None
                self.query = None
                self.difficulty = "easy"
                self.quiz_type = "mcq"
                self.requested_question_count = 1
                self.status = QuizGenerationJobStatus.succeeded
                self.error_code = None
                self.error_message = None
                self.suggestion = None
                self.selected_chunk_ids = []
                self.source_pack = []
                self.created_quiz_id = None
                self.warning = None
                self.warnings = []
                self.fallback_used = False
                self.created_at = None
                self.completed_at = None

            @property
            def updated_at(self):
                raise RuntimeError("lazy load attempted")

        output = service._job_out(ExpiredJob())

        self.assertIsNone(output.updated_at)

    def test_duplicate_questions_are_deduped_and_filled_with_fallback(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(duplicate_questions_json(), [chunk])

        response = asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 2, "easy", "mcq"
            )
        )

        self.assertIsNotNone(response.quiz)
        self.assertEqual(len(response.quiz.questions), 2)
        stems = [service._normalize_question_stem(question.question) for question in response.quiz.questions]
        self.assertEqual(len(stems), len(set(stems)))
        self.assertTrue(response.job.warnings)
        self.assertIn("Duplicate model-generated questions", response.job.warnings[0])

    def test_generate_with_job_status_transitions(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(), [chunk])

        asyncio.run(
            service.generate_with_job(
                uuid4(), uuid4(), chunk.document_id, None, 1, "hard", "mcq"
            )
        )

        statuses = [
            update["status"]
            for update in service.repository.job_updates
            if "status" in update
        ]
        self.assertIn(QuizGenerationJobStatus.retrieving, statuses)
        self.assertIn(QuizGenerationJobStatus.building_context, statuses)
        self.assertIn(QuizGenerationJobStatus.generating, statuses)
        self.assertIn(QuizGenerationJobStatus.validating, statuses)
        self.assertEqual(statuses[-1], QuizGenerationJobStatus.succeeded)

    def test_failed_job_does_not_create_broken_quiz_when_fallback_disabled(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(["not json", "still not json"], [chunk])

        original = settings.quiz_enable_deterministic_fallback
        settings.quiz_enable_deterministic_fallback = False
        try:
            with self.assertRaisesRegex(ValueError, "Check backend QUIZ_DEBUG logs"):
                asyncio.run(
                    service.generate_with_job(
                        uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
                    )
                )
        finally:
            settings.quiz_enable_deterministic_fallback = original

        job = service.repository.jobs[0]
        self.assertEqual(job.status, QuizGenerationJobStatus.failed)
        self.assertEqual(job.error_code, "QUIZ_INVALID_JSON")
        self.assertIsNone(service.repository.created)

    def test_difficulty_prompt_contains_distinct_rules(self) -> None:
        service = self.build_service(quiz_json(), [])

        easy = service._build_prompt("ctx", 1, "easy", "mcq")
        medium = service._build_prompt("ctx", 1, "medium", "mcq")
        hard = service._build_prompt("ctx", 1, "hard", "mcq")

        self.assertIn("For EASY", easy)
        self.assertIn("direct recall", easy)
        self.assertIn("For MEDIUM", medium)
        self.assertIn("understanding", medium)
        self.assertIn("For HARD", hard)
        self.assertIn("scenario-based", hard)

    def test_prompt_uses_previous_question_stems_to_avoid_repeats(self) -> None:
        service = self.build_service(quiz_json(), [])

        prompt = service._build_prompt("ctx", 1, "medium", "mcq", ["What is repeated?"])

        self.assertIn("Avoid repeating these existing question stems", prompt)
        self.assertIn("What is repeated?", prompt)

    def test_quiz_tool_runs_record_validation_failures(self) -> None:
        chunk = retrieved_chunk()
        service = self.build_service(quiz_json(source_index=99), [chunk])

        with self.assertRaisesRegex(ValueError, "invalid source indexes"):
            asyncio.run(
                service.generate_from_document_or_query(
                    uuid4(), uuid4(), chunk.document_id, None, 1, "easy", "mcq"
                )
            )

        self.assertTrue(service.tool_runs.failures)
        self.assertIn("invalid source indexes", service.tool_runs.failures[-1])


if __name__ == "__main__":
    unittest.main()
