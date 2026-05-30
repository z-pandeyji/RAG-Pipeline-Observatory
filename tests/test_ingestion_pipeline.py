import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import fitz

from apps.api.app.db.models import DocumentStatus, SourceType
from apps.api.app.schemas.quizzes import QuizOut
from apps.api.app.services.chunking import SemanticChunkingService
from apps.api.app.services.documents import DocumentService
from apps.api.app.services.embeddings.base import EmbeddingProvider, EmbeddingRequest
from apps.api.app.services.embeddings.base import EmbeddingResponse
from apps.api.app.services.ingestion import IngestionService
from apps.api.app.services.llm.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from apps.api.app.services.pdf_extraction import ExtractedPage, PdfExtractionService
from apps.api.app.services.qdrant import QdrantService


class FakeDocumentRepository:
    def __init__(self, document) -> None:
        self.document = document

    async def get_scoped(self, document_id, workspace_id, user_id):
        return self.document


class FakeDocumentService:
    def __init__(self) -> None:
        self.transitions: list[tuple[DocumentStatus, str | None]] = []

    async def update_status(
        self,
        document,
        status: DocumentStatus,
        page_count: int | None = None,
        error_message: str | None = None,
    ):
        document.status = status
        document.page_count = page_count or document.page_count
        document.error_message = error_message
        self.transitions.append((status, error_message))
        return document


class FakeToolRuns:
    async def start(self, workspace_id, user_id, tool_name, input_):
        return SimpleNamespace(id=uuid4(), tool_name=tool_name)

    async def finish_success(self, run, output):
        return run

    async def finish_failure(self, run, error):
        run.error = error
        return run


class FailingPdfExtractor:
    def extract_pages(self, pdf_path: str):
        raise ValueError("bad pdf")


class FakeEmbeddingProvider(EmbeddingProvider):
    provider_name = "fake"

    async def _embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[0.1, 0.2, 0.3] for _ in request.texts],
            model=request.model,
            provider=self.provider_name,
        )


class FakeLLMProvider(LLMProvider):
    provider_name = "fake"

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="ok", model=request.model, provider=self.provider_name)


class IngestionPipelineTests(unittest.TestCase):
    def test_pdf_extraction_preserves_page_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp).joinpath("sample.pdf")
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Secure RAG page text")
            document.save(pdf_path)
            document.close()

            pages = PdfExtractionService().extract_pages(pdf_path.as_posix())

        self.assertEqual(pages[0].page_number, 1)
        self.assertIn("Secure RAG page text", pages[0].text)

    def test_chunking_uses_page_metadata_and_overlap(self) -> None:
        page = ExtractedPage(
            page_number=3,
            text="First paragraph has useful context. Second paragraph has more detail. " * 20,
        )
        chunks = SemanticChunkingService(target_chars=180, overlap_chars=30).chunk_pages([page])

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.page_number == 3 for chunk in chunks))
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].metadata["chunking"], "semantic_paragraph_overlap")

    def test_document_status_policy_allows_ingestion_transitions(self) -> None:
        service = DocumentService(session=None)

        self.assertTrue(service.can_transition(DocumentStatus.uploaded, DocumentStatus.processing))
        self.assertTrue(service.can_transition(DocumentStatus.processing, DocumentStatus.indexed))
        self.assertTrue(service.can_transition(DocumentStatus.processing, DocumentStatus.failed))
        self.assertFalse(service.can_transition(DocumentStatus.uploaded, DocumentStatus.indexed))

    def test_quiz_create_response_does_not_expose_answer_key(self) -> None:
        response = QuizOut(
            quiz_id=uuid4(),
            title="Quiz",
            questions=[{"question_id": "q1", "question": "Question only", "type": "mcq"}],
            tool_run_id=uuid4(),
        )

        self.assertNotIn("answer_key", response.model_dump())

    def test_qdrant_payload_contains_workspace_and_user(self) -> None:
        workspace_id = uuid4()
        user_id = uuid4()
        payload = QdrantService().chunk_payload(
            chunk_id=uuid4(),
            document_id=uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            source_type="pdf",
            page_number=7,
            chunk_index=2,
        )

        self.assertEqual(payload["workspace_id"], str(workspace_id))
        self.assertEqual(payload["user_id"], str(user_id))
        self.assertEqual(payload["page_number"], 7)

    def test_ingestion_failure_sets_document_failed(self) -> None:
        workspace_id = uuid4()
        user_id = uuid4()
        document = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            source_type=SourceType.pdf,
            status=DocumentStatus.uploaded,
            blob_uri="/missing.pdf",
            page_count=0,
            error_message=None,
        )
        service = IngestionService(session=None, embedding_provider=FakeEmbeddingProvider())
        fake_documents = FakeDocumentService()
        service.documents = fake_documents
        service.document_repository = FakeDocumentRepository(document)
        service.tool_runs = FakeToolRuns()
        service.pdf_extractor = FailingPdfExtractor()

        with self.assertRaises(ValueError):
            asyncio.run(service.process_document(document.id, workspace_id, user_id))

        self.assertEqual(document.status, DocumentStatus.failed)
        self.assertEqual(document.error_message, "bad pdf")
        self.assertIn((DocumentStatus.processing, None), fake_documents.transitions)
        self.assertIn((DocumentStatus.failed, "bad pdf"), fake_documents.transitions)

    def test_llm_and_embedding_providers_use_base_abstractions(self) -> None:
        llm = FakeLLMProvider()
        embedding = FakeEmbeddingProvider()

        llm_response = asyncio.run(
            llm.complete(LLMRequest(model="gemma", messages=[LLMMessage(role="user", content="q")]))
        )
        embedding_response = asyncio.run(
            embedding.embed(EmbeddingRequest(model="embed", texts=["untrusted text"]))
        )

        self.assertEqual(llm_response.provider, "fake")
        self.assertEqual(embedding_response.provider, "fake")
        self.assertEqual(len(embedding_response.vectors), 1)


if __name__ == "__main__":
    unittest.main()
