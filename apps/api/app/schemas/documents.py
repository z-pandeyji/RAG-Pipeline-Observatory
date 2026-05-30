from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from apps.api.app.db.models import DocumentStatus, SourceType


class DocumentCreate(BaseModel):
    workspace_id: UUID
    user_id: UUID
    filename: str
    source_type: SourceType = SourceType.pdf
    content_hash: str | None = None
    blob_uri: str | None = None


class DocumentStatusUpdate(BaseModel):
    status: DocumentStatus
    page_count: int | None = None
    error_message: str | None = None


class DocumentOut(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    filename: str
    source_type: SourceType
    status: DocumentStatus
    page_count: int
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentListItem(DocumentOut):
    chunk_count: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class DocumentDeleteResponse(BaseModel):
    deleted: bool
    document_id: UUID | None = None
    deleted_count: int | None = None
    message: str


class DocumentChunkOut(BaseModel):
    id: UUID
    document_id: UUID
    workspace_id: UUID
    user_id: UUID
    chunk_index: int
    page_number: int | None = None
    source_type: SourceType
    text: str
    metadata: dict

    model_config = {"from_attributes": True}
