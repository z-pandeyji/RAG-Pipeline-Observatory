from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.core.config import settings
from apps.api.app.schemas.lab import ModelHarnessOut, QuizJobTraceOut, SecurityChecks
from apps.api.app.schemas.quizzes import QuizAttemptRequest, QuizAttemptResponse
from apps.api.app.schemas.quizzes import (
    QuizCreateRequest,
    QuizDeleteResponse,
    QuizGenerateResponse,
    QuizGenerationJobDebugResponse,
    QuizGenerationJobListResponse,
    QuizGenerationJobOut,
    QuizListResponse,
    QuizOut,
)
from apps.api.app.services.quizzes import QUIZ_SYSTEM_PROMPT, QuizInvalidJSONError, QuizService

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("", response_model=QuizOut)
async def create_quiz(
    request: QuizCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> QuizOut:
    response = await generate_quiz(request, session)
    if isinstance(response, JSONResponse):
        return response
    if response.quiz is None:
        raise HTTPException(status_code=422, detail="Quiz generation did not create a quiz.")
    return response.quiz


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quiz(
    request: QuizCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> QuizGenerateResponse:
    service = QuizService(session)
    try:
        response = await service.generate_with_job(
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            document_id=request.document_id,
            query=request.query,
            question_count=request.question_count,
            difficulty=request.difficulty,
            quiz_type=request.quiz_type,
        )
    except QuizInvalidJSONError as exc:
        if settings.quiz_auto_retry_smaller and request.question_count > 3:
            response = await service.generate_with_job(
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                document_id=request.document_id,
                query=request.query,
                question_count=3,
                difficulty=request.difficulty,
                quiz_type=request.quiz_type,
            )
            await session.commit()
            return response
        await session.commit()
        return _quiz_error_response(
            str(exc),
            "QUIZ_INVALID_JSON",
            "Try fewer questions or a smaller model/context.",
            exc,
        )
    except ValueError as exc:
        if settings.quiz_auto_retry_smaller and request.question_count > 3:
            response = await service.generate_with_job(
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                document_id=request.document_id,
                query=request.query,
                question_count=3,
                difficulty=request.difficulty,
                quiz_type=request.quiz_type,
            )
            await session.commit()
            return response
        code = _quiz_error_code(str(exc))
        await session.commit()
        return _quiz_error_response(
            str(exc),
            code,
            "Try fewer questions, a different difficulty, or a smaller context.",
            exc,
        )
    await session.commit()
    return response


def _quiz_error_code(message: str) -> str:
    if "invalid source indexes" in message:
        return "QUIZ_SOURCE_INDEX_INVALID"
    if "MCQ" in message or "option" in message:
        return "QUIZ_MCQ_INVALID_OPTIONS"
    if "Insufficient" in message or "evidence" in message.lower():
        return "INSUFFICIENT_EVIDENCE"
    if "JSON" in message:
        return "QUIZ_SCHEMA_VALIDATION_FAILED"
    return "QUIZ_VALIDATION_FAILED"


def _quiz_error_response(message: str, error_code: str, suggestion: str, exc: Exception) -> JSONResponse:
    body = {"detail": message, "error_code": error_code, "suggestion": suggestion}
    if settings.debug_quiz_generation:
        body["debug"] = {
            "parse_error": str(exc),
            "repair_attempted": True,
            "raw_response_preview": "See backend QUIZ_DEBUG logs.",
        }
    return JSONResponse(status_code=422, content=body)


@router.get("", response_model=QuizListResponse)
async def list_quizzes(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizListResponse:
    return QuizListResponse(quizzes=await QuizService(session).list_quizzes(workspace_id, user_id))


@router.get("/jobs", response_model=QuizGenerationJobListResponse)
async def list_generation_jobs(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizGenerationJobListResponse:
    jobs = await QuizService(session).list_generation_jobs(workspace_id, user_id)
    return QuizGenerationJobListResponse(jobs=jobs)


@router.get("/jobs/{job_id}", response_model=QuizGenerationJobOut)
async def get_generation_job(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizGenerationJobOut:
    try:
        return await QuizService(session).get_generation_job(job_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/debug", response_model=QuizGenerationJobDebugResponse)
async def get_generation_job_debug(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizGenerationJobDebugResponse:
    if not settings.debug_quiz_generation:
        raise HTTPException(status_code=403, detail="Quiz debug view is disabled.")
    try:
        return await QuizService(session).get_generation_job_debug(job_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/trace", response_model=QuizJobTraceOut)
async def get_generation_job_trace(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizJobTraceOut:
    try:
        debug = await QuizService(session).get_generation_job_debug(job_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    context_prompt = "\n\n".join(
        str(source.get("text") or source.get("text_preview") or "") for source in debug.source_pack
    )
    return QuizJobTraceOut(
        job_id=debug.job_id,
        source_pack=debug.source_pack,
        prompts={
            "system": QUIZ_SYSTEM_PROMPT,
            "user": debug.prompt_text,
            "context": context_prompt,
            "final": debug.prompt_text,
            "note": "Backend retrieves scoped DB chunks and sends source text to the model; the model does not access the database.",
        },
        raw_llm_response=debug.raw_llm_response,
        extracted_json=debug.extracted_json,
        validation_errors=debug.validation_errors,
        fallback_used=debug.fallback_used,
        warnings=debug.warnings,
        timings=debug.timings,
        model_harness=_model_harness(),
        security_checks=SecurityChecks(
            file_validation="PDF upload validation happens before ingestion; quiz generation uses scoped chunks.",
        ),
    )


def _model_harness() -> ModelHarnessOut:
    return ModelHarnessOut(
        provider=settings.llm_provider,
        model=settings.llm_model,
        json_mode=settings.ollama_json_mode,
        temperature=settings.quiz_temperature,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        qdrant_collection=settings.qdrant_collection,
        fallback={
            "auto_retry_smaller": settings.quiz_auto_retry_smaller,
            "deterministic_quiz_fallback": settings.quiz_enable_deterministic_fallback,
            "max_repair_attempts": settings.quiz_max_repair_attempts,
            "option_repair_enabled": settings.quiz_option_repair_enabled,
        },
    )


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizOut:
    try:
        return await QuizService(session).get_quiz(quiz_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{quiz_id}", response_model=QuizDeleteResponse)
async def delete_quiz(
    quiz_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> QuizDeleteResponse:
    try:
        await QuizService(session).delete_quiz(quiz_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return QuizDeleteResponse(deleted=True, quiz_id=quiz_id)


@router.post("/{quiz_id}/attempt", response_model=QuizAttemptResponse)
async def submit_attempt(
    quiz_id: UUID,
    request: QuizAttemptRequest,
    session: AsyncSession = Depends(get_session),
) -> QuizAttemptResponse:
    try:
        response = await QuizService(session).submit_attempt(
            quiz_id,
            request.workspace_id,
            request.user_id,
            request.question_id,
            request.user_answer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return response


@router.post("/{quiz_id}/attempts", response_model=QuizAttemptResponse)
async def submit_attempt_compat(
    quiz_id: UUID,
    request: QuizAttemptRequest,
    session: AsyncSession = Depends(get_session),
) -> QuizAttemptResponse:
    return await submit_attempt(quiz_id, request, session)
