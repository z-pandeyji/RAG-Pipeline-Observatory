from uuid import UUID

from pydantic import BaseModel, Field


class RequestScope(BaseModel):
    workspace_id: UUID
    user_id: UUID


class CitationOut(BaseModel):
    document_id: UUID
    chunk_id: UUID
    page_number: int | None = None
    timestamp: str | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    url: str | None = None
    image_region: dict | None = None
    metadata: dict = Field(default_factory=dict)
    source_type: str
    text_snippet: str = Field(min_length=1)
