import asyncio
import unittest
from unittest.mock import patch

from apps.api.app.services.llm.base import LLMMessage, LLMRequest
from apps.api.app.services.llm.ollama import OllamaProvider


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"content": '{"questions": []}'}}


class FakeAsyncClient:
    def __init__(self) -> None:
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, json: dict):
        self.payload = json
        return FakeResponse()


class OllamaProviderTests(unittest.TestCase):
    def test_ollama_provider_sends_json_format_when_enabled(self) -> None:
        fake_client = FakeAsyncClient()

        with patch("apps.api.app.services.llm.ollama.settings.ollama_json_mode", True):
            with patch(
                "apps.api.app.services.llm.ollama.httpx.AsyncClient",
                return_value=fake_client,
            ):
                asyncio.run(
                    OllamaProvider().generate_json(
                        LLMRequest(
                            model="gemma",
                            messages=[LLMMessage(role="user", content="Return JSON")],
                        )
                    )
                )

        self.assertEqual(fake_client.payload["format"], "json")
        self.assertEqual(fake_client.payload["options"]["temperature"], 0.0)
        self.assertEqual(fake_client.payload["options"]["num_ctx"], 4096)


if __name__ == "__main__":
    unittest.main()
