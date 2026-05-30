from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.schemas.generation import GenerationRequest, GenerationResponse
from apps.api.app.services.generation import GenerationService

router = APIRouter(prefix="/generation", tags=["generation"])


@router.post("/answer", response_model=GenerationResponse)
async def answer(
    request: GenerationRequest,
    session: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    try:
        response = await GenerationService(session).answer(
            request.workspace_id,
            request.user_id,
            request.query,
            request.document_ids,
            request.source_type,
            request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return response
