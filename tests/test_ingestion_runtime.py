import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.app import main as api_main
from apps.api.app.core.config import settings
from apps.api.app.schemas.quizzes import QuizGenerationJobDebugResponse
from apps.api.app.services.ingestion import (
    DocumentNotFoundInWorkspaceError,
    IngestionService,
    QdrantUpsertFailedError,
)
from apps.api.app.services.quizzes import QuizInvalidJSONError
from apps.api.app.services.youtube import YouTubeTranscriptUnavailableError


class FakeDocumentRepository:
    async def get_scoped(self, document_id, workspace_id, user_id):
        return None


class FakeDocuments:
    async def update_status(self, document, status, page_count=None, error_message=None):
        document.status = status
        document.error_message = error_message
        return document


class FakeToolRuns:
    async def start(self, workspace_id, user_id, tool_name, input_):
        return SimpleNamespace(id=uuid4())

    async def finish_success(self, run, output):
        return run

    async def finish_failure(self, run, error):
        return run


class IngestionRuntimeTests(TestCase):
    def test_cors_allows_localhost_origin(self) -> None:
        client = TestClient(api_main.app)

        response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_ingest_route_exists_at_expected_path(self) -> None:
        routes = {route.path for route in api_main.app.routes if hasattr(route, "path")}

        self.assertIn("/api/documents/{document_id}/ingest", routes)

    def test_frontend_api_client_uses_env_base_url_for_ingest(self) -> None:
        api_client_source = Path("apps/web/lib/api-client.ts").read_text()

        self.assertIn(
            'process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"',
            api_client_source,
        )
        self.assertIn("/api/documents/${documentId}/ingest", api_client_source)

    def test_frontend_api_client_has_workspace_list_methods(self) -> None:
        api_client_source = Path("apps/web/lib/api-client.ts").read_text()

        self.assertIn("async listDocuments", api_client_source)
        self.assertIn("`${API_BASE_URL}/api/documents?${query", api_client_source)
        self.assertIn("async listQuizzes", api_client_source)
        self.assertIn("`${API_BASE_URL}/api/quizzes?${query", api_client_source)
        self.assertIn("async deleteDocument", api_client_source)
        self.assertIn("async clearFailedDocuments", api_client_source)
        self.assertIn("async deleteQuiz", api_client_source)

    def test_dashboard_rehydrates_workspace_state_on_load(self) -> None:
        page_source = Path("apps/web/app/page.tsx").read_text()

        self.assertIn("apiClient.listDocuments(workspaceId, userId)", page_source)
        self.assertIn("apiClient.listQuizzes(workspaceId, userId)", page_source)
        self.assertIn('window.localStorage.getItem("selectedDocumentId")', page_source)
        self.assertIn('window.localStorage.getItem("activeTab")', page_source)

    def test_frontend_api_client_debug_flag_does_not_change_generate_quiz_route(self) -> None:
        api_client_source = Path("apps/web/lib/api-client.ts").read_text()

        self.assertIn('process.env.NEXT_PUBLIC_DEBUG_API === "true"', api_client_source)
        self.assertIn('debugApi("generateQuiz request payload", input)', api_client_source)
        self.assertIn("`${API_BASE_URL}/api/quizzes/generate`", api_client_source)
        self.assertIn("async getQuizGenerationJobDebug", api_client_source)

    def test_legacy_ask_tab_not_visible_but_chat_tab_is_available(self) -> None:
        page_source = Path("apps/web/app/page.tsx").read_text()

        self.assertNotIn('["ask", "Ask"]', page_source)
        self.assertIn('"Chat"', page_source)
        self.assertIn("<ChatPanel", page_source)

    def test_quiz_debug_panel_is_gated_by_frontend_debug_flag(self) -> None:
        panel_source = Path("apps/web/features/quiz/QuizPanel.tsx").read_text()

        self.assertIn("isApiDebugEnabled", panel_source)
        self.assertIn("Quiz generation debug", panel_source)
        self.assertIn("Debug data may include hidden answer information", panel_source)
        self.assertIn("Prompt sent to model", panel_source)
        self.assertIn("Model response", panel_source)

    def test_processing_timeline_has_clear_timestamp_fallbacks(self) -> None:
        timeline_source = Path("apps/web/features/processing-panel/ProcessingTimeline.tsx").read_text()

        self.assertIn('return run.created_at ? new Date(run.created_at).toLocaleString() : "-"', timeline_source)
        self.assertIn('if (run.status === "running") return "In progress"', timeline_source)
        self.assertIn('if (run.status === "queued") return "Not started"', timeline_source)
        self.assertIn('if (run.status === "failed") return "Failed"', timeline_source)
        self.assertIn('if (run.status === "succeeded") return "Completed"', timeline_source)
        self.assertIn('"youtube_audio_download"', timeline_source)
        self.assertIn('"youtube_audio_transcription"', timeline_source)

    def test_auto_create_tables_is_disabled_by_default(self) -> None:
        self.assertFalse(settings.auto_create_tables)

    def test_local_init_db_does_not_drop_tables(self) -> None:
        init_db_source = Path("apps/api/app/db/init_db.py").read_text()

        self.assertIn("create_all", init_db_source)
        self.assertNotIn("drop_all", init_db_source)

    def test_startup_only_runs_init_db_when_enabled(self) -> None:
        with patch.object(api_main, "init_db", new=AsyncMock()) as init_db_mock:
            with patch.object(settings, "auto_create_tables", True):
                asyncio.run(api_main.startup())

        init_db_mock.assert_awaited_once()

    def test_startup_does_not_run_init_db_when_disabled(self) -> None:
        with patch.object(api_main, "init_db", new=AsyncMock()) as init_db_mock:
            with patch.object(settings, "auto_create_tables", False):
                asyncio.run(api_main.startup())

        init_db_mock.assert_not_awaited()

    def test_ingest_route_returns_404_for_workspace_mismatch(self) -> None:
        client = TestClient(api_main.app)
        document_id = uuid4()
        detail = "Document not found for this workspace/user."

        with patch(
            "apps.api.app.routers.documents.IngestionService.process_document",
            new=AsyncMock(side_effect=DocumentNotFoundInWorkspaceError(detail)),
        ):
            response = client.post(
                f"/api/documents/{document_id}/ingest",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], detail)

    def test_youtube_ingest_returns_503_when_transcript_unavailable(self) -> None:
        client = TestClient(api_main.app)
        detail = "No public transcript extractor configured for video bMTlNeKqV4o. Future audio transcription should implement this interface."

        with patch(
            "apps.api.app.routers.documents.IngestionService.process_document",
            new=AsyncMock(side_effect=YouTubeTranscriptUnavailableError(detail)),
        ):
            response = client.post(
                "/api/documents/00000000-0000-0000-0000-000000000001/ingest",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], detail)

    def test_ingest_route_returns_400_for_qdrant_upsert_diagnostics(self) -> None:
        client = TestClient(api_main.app)
        detail = (
            "Qdrant upsert failed for collection 'learning_chunks' "
            "(expected vector dimension 1024, actual 1024). Qdrant 400: vector size mismatch"
        )

        with patch(
            "apps.api.app.routers.documents.IngestionService.process_document",
            new=AsyncMock(side_effect=QdrantUpsertFailedError(detail)),
        ):
            response = client.post(
                "/api/documents/00000000-0000-0000-0000-000000000001/ingest",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], detail)

    def test_quiz_generate_invalid_json_returns_422(self) -> None:
        client = TestClient(api_main.app)
        detail = "Quiz generation returned invalid JSON. Check backend QUIZ_DEBUG logs."

        with patch(
            "apps.api.app.routers.quizzes.QuizService.generate_with_job",
            new=AsyncMock(side_effect=QuizInvalidJSONError(detail)),
        ):
            response = client.post(
                "/api/quizzes/generate",
                json={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                    "question_count": 3,
                    "difficulty": "medium",
                    "quiz_type": "mcq",
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], detail)
        self.assertEqual(response.json()["error_code"], "QUIZ_INVALID_JSON")

    def test_quiz_job_debug_endpoint_disabled_by_default(self) -> None:
        client = TestClient(api_main.app)

        with patch.object(settings, "debug_quiz_generation", False):
            response = client.get(
                f"/api/quizzes/jobs/{uuid4()}/debug",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Quiz debug view is disabled.")

    def test_quiz_job_debug_endpoint_returns_debug_when_enabled(self) -> None:
        client = TestClient(api_main.app)
        job_id = uuid4()
        workspace_id = UUID("00000000-0000-0000-0000-000000000001")
        user_id = UUID("00000000-0000-0000-0000-000000000001")
        debug_response = QuizGenerationJobDebugResponse(
            job_id=job_id,
            status="succeeded",
            difficulty="medium",
            quiz_type="mcq",
            requested_question_count=3,
            selected_chunk_ids=["chunk-1"],
            source_pack=[{"source_index": 0, "text_preview": "preview", "text": "full"}],
            prompt_text="Prompt sent to model",
            raw_llm_response='{"questions":[]}',
            extracted_json='{"questions":[]}',
            repaired_llm_response=None,
            validation_errors=[],
            fallback_used=False,
            warnings=[],
            timings={},
        )

        with patch.object(settings, "debug_quiz_generation", True):
            with patch(
                "apps.api.app.routers.quizzes.QuizService.get_generation_job_debug",
                new=AsyncMock(return_value=debug_response),
            ) as debug_mock:
                response = client.get(
                    f"/api/quizzes/jobs/{job_id}/debug",
                    params={
                        "workspace_id": str(workspace_id),
                        "user_id": str(user_id),
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["prompt_text"], "Prompt sent to model")
        debug_mock.assert_awaited_once_with(job_id, workspace_id, user_id)

    def test_delete_document_route_is_scoped(self) -> None:
        client = TestClient(api_main.app)
        document_id = uuid4()

        with patch(
            "apps.api.app.routers.documents.DocumentService.delete_document",
            new=AsyncMock(side_effect=ValueError("Document not found for this workspace/user.")),
        ):
            response = client.delete(
                f"/api/documents/{document_id}",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 404)

    def test_delete_failed_documents_route_returns_count(self) -> None:
        client = TestClient(api_main.app)

        with patch(
            "apps.api.app.routers.documents.DocumentService.delete_failed_documents",
            new=AsyncMock(return_value=2),
        ):
            response = client.delete(
                "/api/documents/failed",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_count"], 2)

    def test_delete_quiz_route_is_scoped(self) -> None:
        client = TestClient(api_main.app)
        quiz_id = uuid4()

        with patch(
            "apps.api.app.routers.quizzes.QuizService.delete_quiz",
            new=AsyncMock(side_effect=ValueError("Quiz not found for this workspace/user.")),
        ):
            response = client.delete(
                f"/api/quizzes/{quiz_id}",
                params={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        self.assertEqual(response.status_code, 404)


class IngestionServiceScopeTests(IsolatedAsyncioTestCase):
    async def test_workspace_mismatch_raises_clear_error(self) -> None:
        service = IngestionService(session=None)
        service.document_repository = FakeDocumentRepository()
        service.documents = FakeDocuments()
        service.tool_runs = FakeToolRuns()

        with self.assertRaises(DocumentNotFoundInWorkspaceError) as context:
            await service.process_document(
                uuid4(),
                UUID("00000000-0000-0000-0000-000000000001"),
                UUID("00000000-0000-0000-0000-000000000001"),
            )

        self.assertIn("Document not found for this workspace/user.", str(context.exception))


if __name__ == "__main__":
    import unittest

    unittest.main()
