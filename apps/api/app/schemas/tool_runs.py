from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from apps.api.app.db.models import ToolRunStatus


class ToolRunOut(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    tool_name: str
    status: ToolRunStatus
    input: dict
    output: dict
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
