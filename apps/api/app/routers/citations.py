from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Citation
from apps.api.app.db.session import get_session
from apps.api.app.schemas.common import CitationOut

router = APIRouter(prefix="/citations", tags=["citations"])


@router.get("", response_model=list[CitationOut])
async def list_citations(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[CitationOut]:
    result = await session.execute(
        select(Citation)
        .where(Citation.workspace_id == workspace_id, Citation.user_id == user_id)
        .order_by(Citation.created_at.desc())
    )
    return [
        CitationOut(
            document_id=citation.document_id,
            chunk_id=citation.chunk_id,
            page_number=citation.page_number,
            timestamp=citation.timestamp,
            source_type=citation.source_type.value,
            text_snippet=citation.text_snippet,
        )
        for citation in result.scalars().all()
    ]
