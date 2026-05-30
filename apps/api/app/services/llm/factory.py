from apps.api.app.core.config import settings
from apps.api.app.services.llm.base import LLMProvider
from apps.api.app.services.llm.lmstudio import LMStudioProvider
from apps.api.app.services.llm.ollama import OllamaProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    return LMStudioProvider()
