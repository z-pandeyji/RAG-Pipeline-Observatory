from uuid import UUID

from pydantic import BaseModel

from apps.api.app.db.models import SourceType


class IngestionRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    source_type: SourceType = SourceType.pdf


class IngestionResponse(BaseModel):
    document_id: UUID
    status: str
    tool_run_id: UUID
    workspace_id: UUID | None = None
    user_id: UUID | None = None
    filename: str | None = None
    source_type: SourceType | None = None


class YouTubeIngestionRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    youtube_url: str
    title: str | None = None
