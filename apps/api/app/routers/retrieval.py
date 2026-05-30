from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from apps.api.app.services.retrieval import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/query", response_model=RetrievalResponse)
async def retrieve(
    request: RetrievalRequest,
    session: AsyncSession = Depends(get_session),
) -> RetrievalResponse:
    chunks, tool_run_id = await RetrievalService(session).retrieve(
        request.workspace_id,
        request.user_id,
        request.query,
        request.document_ids,
        request.top_k,
        request.source_type,
    )
    await session.commit()
    return RetrievalResponse(chunks=chunks, tool_run_id=tool_run_id)
