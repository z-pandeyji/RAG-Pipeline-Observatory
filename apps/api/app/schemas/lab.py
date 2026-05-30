from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.app.schemas.documents import DocumentChunkOut, DocumentOut
from apps.api.app.schemas.tool_runs import ToolRunOut


class DatasetStats(BaseModel):
    page_count: int = 0
    character_count: int = 0
    word_count: int = 0
    chunk_count: int = 0
    avg_chunk_size: int = 0


class PageStats(BaseModel):
    page_number: int | None = None
    character_count: int = 0
    word_count: int = 0
    chunk_count: int = 0


class EmbeddingSummary(BaseModel):
    provider: str
    model: str
    dimensions: int
    vector_count: int = 0
    chunk_target_chars: int
    chunk_overlap_chars: int


class QdrantSummary(BaseModel):
    collection: str
    vector_store: str = "qdrant"
    vector_count: int = 0
    filter: dict[str, Any] = Field(default_factory=dict)


class SecurityChecks(BaseModel):
    pdf_only: bool = True
    file_validation: str
    workspace_user_filter: bool = True
    qdrant_filter: bool = True
    hidden_answer_key: bool = True
    attempt_grading: bool = True
    untrusted_pdf_text: bool = True
    local_model_no_db_access: bool = True


class ModelHarnessOut(BaseModel):
    provider: str
    model: str
    json_mode: bool
    temperature: float
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    vector_store: str = "qdrant"
    qdrant_collection: str
    fallback: dict[str, Any]


class DocumentRagTraceOut(BaseModel):
    document: DocumentOut
    dataset_stats: DatasetStats
    pages: list[PageStats]
    chunks: list[DocumentChunkOut]
    embedding_summary: EmbeddingSummary
    qdrant_summary: QdrantSummary
    security_checks: SecurityChecks
    tool_runs: list[ToolRunOut]


class QuizJobTraceOut(BaseModel):
    job_id: UUID
    source_pack: list[dict[str, Any]] = Field(default_factory=list)
    prompts: dict[str, Any] = Field(default_factory=dict)
    raw_llm_response: str | None = None
    extracted_json: str | None = None
    validation_errors: list[Any] = Field(default_factory=list)
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    timings: dict[str, Any] = Field(default_factory=dict)
    model_harness: ModelHarnessOut
    security_checks: SecurityChecks
