from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.app.schemas.common import CitationOut


class RetrievalRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    query: str = Field(min_length=1)
    document_ids: list[UUID] = Field(default_factory=list)
    source_type: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)

    @property
    def limit(self) -> int:
        return self.top_k


class RetrievedChunkOut(BaseModel):
    document_id: UUID
    chunk_id: UUID
    score: float
    text: str
    citation: CitationOut


class RetrievalResponse(BaseModel):
    chunks: list[RetrievedChunkOut]
    tool_run_id: UUID
