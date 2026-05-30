import httpx

from apps.api.app.core.config import settings
from apps.api.app.services.llm.base import LLMProvider, LLMRequest, LLMResponse


class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if settings.ollama_json_mode and request.structured_json:
            payload["format"] = "json"
            payload["options"] = {"temperature": 0.0, "num_ctx": 4096}
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            response = await client.post(settings.ollama_chat_url, json=payload)
            response.raise_for_status()
        content = response.json()["message"]["content"]
        return LLMResponse(content=content, model=request.model, provider=self.provider_name)
