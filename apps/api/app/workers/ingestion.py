from uuid import UUID

from apps.api.app.db.models import DocumentStatus
from apps.api.app.db.session import AsyncSessionLocal
from apps.api.app.repositories.documents import DocumentRepository
from apps.api.app.services.ingestion import IngestionService


async def process_document(document_id: UUID, workspace_id: UUID, user_id: UUID) -> DocumentStatus:
    async with AsyncSessionLocal() as session:
        await IngestionService(session).process_document(document_id, workspace_id, user_id)
        await session.commit()
        document = await DocumentRepository(session).get_scoped(document_id, workspace_id, user_id)
        if document is None:
            raise ValueError("Document not found for this workspace/user.")
        return document.status


async def process_pending_documents(limit: int = 10) -> int:
    async with AsyncSessionLocal() as session:
        repository = DocumentRepository(session)
        documents = await repository.list_pending(limit)
        processed = 0
        for document in documents:
            await IngestionService(session).process_document(
                document.id,
                document.workspace_id,
                document.user_id,
            )
            processed += 1
        await session.commit()
        return processed
