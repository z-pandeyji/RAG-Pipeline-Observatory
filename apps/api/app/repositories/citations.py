from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Citation, SourceType
from apps.api.app.schemas.common import CitationOut


class CitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(
        self,
        workspace_id: UUID,
        user_id: UUID,
        citations: list[CitationOut],
    ) -> list[Citation]:
        records = [
            Citation(
                workspace_id=workspace_id,
                user_id=user_id,
                document_id=citation.document_id,
                chunk_id=citation.chunk_id,
                page_number=citation.page_number,
                timestamp=citation.timestamp,
                source_type=SourceType(citation.source_type),
                text_snippet=citation.text_snippet,
            )
            for citation in citations
        ]
        self.session.add_all(records)
        await self.session.flush()
        return records
