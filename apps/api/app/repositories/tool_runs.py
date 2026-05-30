from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import ToolRun, ToolRunStatus


class ToolRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(
        self,
        workspace_id: UUID,
        user_id: UUID,
        tool_name: str,
        input_: dict,
    ) -> ToolRun:
        run = ToolRun(
            workspace_id=workspace_id,
            user_id=user_id,
            tool_name=tool_name,
            status=ToolRunStatus.running,
            input=input_,
            output={},
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def succeed(self, run: ToolRun, output: dict) -> ToolRun:
        run.status = ToolRunStatus.succeeded
        run.output = output
        run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def fail(self, run: ToolRun, error: str) -> ToolRun:
        run.status = ToolRunStatus.failed
        run.error = error
        run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def list_scoped(self, workspace_id: UUID, user_id: UUID) -> list[ToolRun]:
        result = await self.session.execute(
            select(ToolRun)
            .where(ToolRun.workspace_id == workspace_id, ToolRun.user_id == user_id)
            .order_by(ToolRun.created_at.desc())
        )
        return list(result.scalars().all())
