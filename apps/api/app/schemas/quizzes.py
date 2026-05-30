from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.app.core.config import settings


class QuizCreateRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    document_id: UUID | None = None
    query: str | None = None
    question_count: int = Field(default=settings.quiz_default_question_count, ge=1, le=5)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    quiz_type: Literal["mcq", "short_answer", "true_false", "mixed"] = "mcq"


class QuizQuestionOut(BaseModel):
    question_id: str
    question: str
    type: str
    options: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    answer_hidden: bool = True


class QuizOut(BaseModel):
    quiz_id: UUID | None = None
    title: str
    questions: list[QuizQuestionOut]
    tool_run_id: UUID | None = None
    evidence_status: Literal["grounded", "insufficient_evidence"] = "grounded"


class QuizGenerationJobOut(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    document_id: UUID | None = None
    query: str | None = None
    difficulty: str
    quiz_type: str
    requested_question_count: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    suggestion: str | None = None
    selected_chunk_ids: list = Field(default_factory=list)
    source_count: int = 0
    created_quiz_id: UUID | None = None
    warning: str | None = None
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class QuizGenerateResponse(BaseModel):
    quiz: QuizOut | None = None
    job: QuizGenerationJobOut


class QuizGenerationJobListResponse(BaseModel):
    jobs: list[QuizGenerationJobOut]


class QuizGenerationJobDebugResponse(BaseModel):
    job_id: UUID
    status: str
    difficulty: str
    quiz_type: str
    requested_question_count: int
    selected_chunk_ids: list[str] = Field(default_factory=list)
    source_pack: list[dict] = Field(default_factory=list)
    prompt_text: str | None = None
    raw_llm_response: str | None = None
    extracted_json: str | None = None
    repaired_llm_response: str | None = None
    validation_errors: list = Field(default_factory=list)
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    timings: dict = Field(default_factory=dict)


class QuizAttemptRequest(BaseModel):
    workspace_id: UUID
    user_id: UUID
    question_id: str
    user_answer: str


class QuizAttemptResponse(BaseModel):
    attempt_id: UUID
    question_id: str
    is_correct: bool
    score: int
    correct_answer: str
    explanation: str
    citations: list[dict]


class QuizListItem(BaseModel):
    quiz_id: UUID
    id: UUID | None = None
    title: str
    document_id: UUID | None = None
    difficulty: str | None = None
    quiz_type: str | None = None
    question_count: int = 0
    created_at: datetime | None = None
    questions: list[QuizQuestionOut] = Field(default_factory=list)
    attempt_summary: dict | None = None
    evidence_status: Literal["grounded"] = "grounded"


class QuizListResponse(BaseModel):
    quizzes: list[QuizListItem]


class QuizDeleteResponse(BaseModel):
    deleted: bool
    quiz_id: UUID
