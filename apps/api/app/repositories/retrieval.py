from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import DocumentChunk


class RetrievalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_candidate_chunks(
        self,
        workspace_id: UUID,
        user_id: UUID,
        document_ids: list[UUID],
        limit: int,
    ) -> list[DocumentChunk]:
        statement = select(DocumentChunk).where(
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.user_id == user_id,
        )
        if document_ids:
            statement = statement.where(DocumentChunk.document_id.in_(document_ids))
        statement = statement.order_by(DocumentChunk.created_at.desc()).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def hydrate_chunks_by_ids(
        self,
        chunk_ids: list[UUID],
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        result = await self.session.execute(
            select(DocumentChunk).where(
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.user_id == user_id,
            )
        )
        by_id = {chunk.id: chunk for chunk in result.scalars().all()}
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]
