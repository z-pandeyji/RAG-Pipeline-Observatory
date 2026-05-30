import httpx

from apps.api.app.core.config import settings
from apps.api.app.services.llm.base import LLMProvider, LLMRequest, LLMResponse


class LMStudioProvider(LLMProvider):
    provider_name = "lmstudio"

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            response = await client.post(settings.lmstudio_chat_url, json=payload)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return LLMResponse(content=content, model=request.model, provider=self.provider_name)
