from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.repositories.tool_runs import ToolRunRepository
from apps.api.app.schemas.tool_runs import ToolRunOut

router = APIRouter(prefix="/tool-runs", tags=["tool_runs"])


@router.get("", response_model=list[ToolRunOut])
async def list_tool_runs(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ToolRunOut]:
    runs = await ToolRunRepository(session).list_scoped(workspace_id, user_id)
    return [ToolRunOut.model_validate(run) for run in runs]
