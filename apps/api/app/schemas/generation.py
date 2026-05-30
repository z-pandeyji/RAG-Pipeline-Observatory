from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.app.schemas.common import CitationOut


class GenerationRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    query: str = Field(min_length=1)
    document_ids: list[UUID] = Field(default_factory=list)
    source_type: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)


class GenerationResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    tool_run_id: UUID
    evidence_status: str
