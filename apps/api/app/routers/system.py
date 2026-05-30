from fastapi import APIRouter

from apps.api.app.core.config import settings
from apps.api.app.schemas.lab import ModelHarnessOut

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/model-harness", response_model=ModelHarnessOut)
async def get_model_harness() -> ModelHarnessOut:
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
