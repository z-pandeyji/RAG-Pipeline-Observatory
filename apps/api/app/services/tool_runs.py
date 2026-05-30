from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import ToolRun
from apps.api.app.repositories.tool_runs import ToolRunRepository

T = TypeVar("T")


class ToolRunLogger:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ToolRunRepository(session)

    async def start(
        self,
        workspace_id: UUID,
        user_id: UUID,
        tool_name: str,
        input_: dict,
    ) -> ToolRun:
        return await self.repository.start(workspace_id, user_id, tool_name, input_)

    async def finish_success(self, run: ToolRun, output: dict) -> ToolRun:
        return await self.repository.succeed(run, output)

    async def finish_failure(self, run: ToolRun, error: str) -> ToolRun:
        return await self.repository.fail(run, error)

    async def tracked(
        self,
        workspace_id: UUID,
        user_id: UUID,
        tool_name: str,
        input_: dict,
        operation: Callable[[ToolRun], Awaitable[T]],
    ) -> tuple[T, ToolRun]:
        run = await self.start(workspace_id, user_id, tool_name, input_)
        try:
            result = await operation(run)
        except Exception as exc:
            await self.finish_failure(run, str(exc))
            raise
        await self.finish_success(run, {"status": "ok"})
        return result, run
