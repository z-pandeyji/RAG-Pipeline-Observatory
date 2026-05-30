import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceType(str, enum.Enum):
    pdf = "pdf"
    image = "image"
    youtube = "youtube"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class ToolRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class QuizAttemptStatus(str, enum.Enum):
    started = "started"
    submitted = "submitted"


class QuizGenerationJobStatus(str, enum.Enum):
    queued = "queued"
    retrieving = "retrieving"
    building_context = "building_context"
    generating = "generating"
    validating = "validating"
    repairing = "repairing"
    succeeded = "succeeded"
    failed = "failed"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="workspace")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.uploaded,
        index=True,
    )
    content_hash: Mapped[str | None] = mapped_column(String(128))
    blob_uri: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    text_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ToolRun(Base):
    __tablename__ = "tool_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[ToolRunStatus] = mapped_column(Enum(ToolRunStatus), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    answer_key: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[QuizAttemptStatus] = mapped_column(Enum(QuizAttemptStatus), nullable=False)
    submitted_answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class QuizGenerationJob(Base):
    __tablename__ = "quiz_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    query: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(24), nullable=False)
    quiz_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QuizGenerationJobStatus] = mapped_column(
        Enum(QuizGenerationJobStatus),
        nullable=False,
        default=QuizGenerationJobStatus.queued,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    selected_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_pack: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    prompt_text: Mapped[str | None] = mapped_column(Text)
    raw_llm_response: Mapped[str | None] = mapped_column(Text)
    extracted_json: Mapped[str | None] = mapped_column(Text)
    repaired_llm_response: Mapped[str | None] = mapped_column(Text)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    fallback_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    timings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_quiz_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    warning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("document_chunks_scope_idx", DocumentChunk.workspace_id, DocumentChunk.user_id)
Index("document_chunks_document_scope_idx", DocumentChunk.document_id, DocumentChunk.workspace_id)
