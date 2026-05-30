from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Document, DocumentStatus, SourceType
from apps.api.app.repositories.documents import DocumentRepository
from apps.api.app.services.qdrant import QdrantService, QdrantUnavailableError


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = DocumentRepository(session)

    async def create_upload(
        self,
        workspace_id: UUID,
        user_id: UUID,
        filename: str,
        source_type: SourceType,
        content_hash: str | None,
        blob_uri: str | None,
    ) -> Document:
        safe_name = Path(filename).name[:500] or "document"
        return await self.repository.create(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=safe_name,
            source_type=source_type,
            content_hash=content_hash,
            blob_uri=blob_uri,
        )

    async def update_status(
        self,
        document: Document,
        status: DocumentStatus,
        page_count: int | None = None,
        error_message: str | None = None,
    ) -> Document:
        if not self.can_transition(document.status, status):
            raise ValueError(f"Invalid document status transition: {document.status} -> {status}.")
        return await self.repository.update_status(document, status, page_count, error_message)

    def can_transition(self, current: DocumentStatus, next_status: DocumentStatus) -> bool:
        allowed = {
            DocumentStatus.uploaded: {DocumentStatus.processing, DocumentStatus.failed},
            DocumentStatus.queued: {DocumentStatus.processing, DocumentStatus.failed},
            DocumentStatus.processing: {DocumentStatus.indexed, DocumentStatus.failed},
            DocumentStatus.indexed: {DocumentStatus.indexed},
            DocumentStatus.failed: {DocumentStatus.processing, DocumentStatus.failed},
        }
        return next_status in allowed[current]

    async def delete_document(self, document_id: UUID, workspace_id: UUID, user_id: UUID) -> dict:
        document = await self.repository.get_scoped(document_id, workspace_id, user_id)
        if document is None:
            raise ValueError("Document not found for this workspace/user.")
        blob_uri = document.blob_uri
        qdrant_summary = {}
        try:
            qdrant_summary = await QdrantService().delete_document_vectors(
                document_id,
                workspace_id,
                user_id,
            )
        except QdrantUnavailableError as exc:
            qdrant_summary = {"warning": str(exc)}
        await self.repository.delete_scoped(document)
        blob_deleted = self._delete_local_blob(blob_uri)
        return {
            "deleted": True,
            "document_id": document_id,
            "blob_deleted": blob_deleted,
            "qdrant": qdrant_summary,
        }

    async def delete_failed_documents(self, workspace_id: UUID, user_id: UUID) -> int:
        documents = await self.repository.delete_failed_scoped(workspace_id, user_id)
        for document in documents:
            self._delete_local_blob(document.blob_uri)
            try:
                await QdrantService().delete_document_vectors(document.id, workspace_id, user_id)
            except QdrantUnavailableError:
                continue
        return len(documents)

    def _delete_local_blob(self, blob_uri: str | None) -> bool:
        if not blob_uri:
            return False
        path = Path(blob_uri)
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True
