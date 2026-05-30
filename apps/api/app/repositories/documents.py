from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Citation, Document, DocumentChunk, DocumentStatus, SourceType, ToolRun


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        workspace_id: UUID,
        user_id: UUID,
        filename: str,
        source_type: SourceType,
        content_hash: str | None,
        blob_uri: str | None,
    ) -> Document:
        document = Document(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=filename,
            source_type=source_type,
            status=DocumentStatus.uploaded,
            content_hash=content_hash,
            blob_uri=blob_uri,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_scoped(
        self,
        document_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
    ) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        document: Document,
        status: DocumentStatus,
        page_count: int | None = None,
        error_message: str | None = None,
    ) -> Document:
        document.status = status
        if page_count is not None:
            document.page_count = page_count
        document.error_message = error_message
        await self.session.flush()
        return document

    async def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()

    async def replace_chunks(self, document: Document, chunks: list[DocumentChunk]) -> None:
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        self.session.add_all(chunks)
        await self.session.flush()

    async def list_chunks_scoped(
        self,
        document_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[DocumentChunk]:
        result = await self.session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.user_id == user_id,
            )
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def list_scoped_with_chunk_counts(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[tuple[Document, int]]:
        result = await self.session.execute(
            select(Document, func.count(DocumentChunk.id))
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(Document.workspace_id == workspace_id, Document.user_id == user_id)
            .group_by(Document.id)
            .order_by(Document.created_at.desc())
        )
        return [(document, int(chunk_count)) for document, chunk_count in result.all()]

    async def delete_scoped(self, document: Document) -> None:
        await self.session.execute(delete(Citation).where(Citation.document_id == document.id))
        await self.session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        await self.session.execute(
            delete(ToolRun).where(
                ToolRun.workspace_id == document.workspace_id,
                ToolRun.user_id == document.user_id,
                ToolRun.input["document_id"].astext == str(document.id),
            )
        )
        await self.session.delete(document)
        await self.session.flush()

    async def delete_failed_scoped(self, workspace_id: UUID, user_id: UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.user_id == user_id,
                Document.status == DocumentStatus.failed,
            )
        )
        documents = list(result.scalars().all())
        for document in documents:
            await self.delete_scoped(document)
        return documents

    async def list_pending(self, limit: int = 10) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.status.in_([DocumentStatus.uploaded, DocumentStatus.queued]))
            .order_by(Document.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
