import asyncio
from datetime import UTC, datetime
from enum import Enum
import unittest
from uuid import uuid4

import httpx

from apps.api.app.core.config import settings
from apps.api.app.services.qdrant import QdrantService, QdrantUpsertError


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", json_data: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}
        self.request = httpx.Request("PUT", "http://qdrant.local")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Qdrant error", request=self.request, response=self)

    def json(self) -> dict:
        return self._json_data


class FakeAsyncClient:
    def __init__(self, get_response: FakeResponse | None = None, put_response: FakeResponse | None = None) -> None:
        self.get_response = get_response or FakeResponse(200)
        self.put_response = put_response or FakeResponse(200)
        self.put_calls: list[dict] = []
        self.post_calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return self.get_response

    async def put(self, url: str, json: dict):
        self.put_calls.append(json)
        return self.put_response

    async def post(self, url: str, json: dict):
        self.post_calls.append(json)
        return self.put_response


class DemoEnum(str, Enum):
    alpha = "alpha"


class QdrantServiceTests(unittest.TestCase):
    def test_vector_dimension_mismatch_raises_clear_error(self) -> None:
        service = QdrantService()

        async def run() -> None:
            from unittest.mock import patch

            with patch.object(settings, "embedding_dimensions", 1024):
                with self.assertRaises(ValueError) as context:
                    await service.upsert_chunks([(uuid4(), [0.1] * 3, {})])

            self.assertEqual(
                str(context.exception),
                "Embedding dimension mismatch: model returned 3 dimensions but EMBEDDING_DIMENSIONS is 1024.",
            )

        asyncio.run(run())

    def test_payload_serializes_uuid_enum_and_datetime(self) -> None:
        service = QdrantService()
        now = datetime(2025, 1, 1, tzinfo=UTC)
        payload = service.chunk_payload(
            chunk_id=uuid4(),
            document_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            source_type=DemoEnum.alpha,
            page_number=7,
            chunk_index=1,
            metadata={
                "image_region": {
                    "chunk_uuid": uuid4(),
                    "mode": DemoEnum.alpha,
                    "captured_at": now,
                }
            },
        )

        self.assertIsInstance(payload["chunk_id"], str)
        self.assertIsInstance(payload["document_id"], str)
        self.assertIsInstance(payload["workspace_id"], str)
        self.assertIsInstance(payload["user_id"], str)
        self.assertEqual(payload["source_type"], "alpha")
        self.assertEqual(payload["image_region"]["mode"], "alpha")
        self.assertEqual(payload["image_region"]["captured_at"], now.isoformat())
        self.assertIsInstance(payload["image_region"]["chunk_uuid"], str)

    def test_qdrant_400_returns_clear_diagnostic_error(self) -> None:
        service = QdrantService()
        fake_client = FakeAsyncClient(
            get_response=FakeResponse(
                200,
                json_data={
                    "result": {
                        "config": {
                            "params": {
                                "vectors": {"size": 768}
                            }
                        }
                    }
                },
            ),
            put_response=FakeResponse(
                400,
                text='{"status":{"error":"Wrong input: Vector dimension error: expected dim: 768, got 1024"},"time":0.00081}',
            ),
        )

        async def run() -> None:
            from unittest.mock import patch

            with patch.object(settings, "embedding_dimensions", 1024):
                with patch("apps.api.app.services.qdrant.httpx.AsyncClient", return_value=fake_client):
                    with self.assertRaises(QdrantUpsertError) as context:
                        await service.upsert_chunks([(uuid4(), [0.1] * 1024, {"foo": "bar"})])

                message = str(context.exception)
                self.assertIn("collection 'learning_chunks'", message)
                self.assertIn("expected vector dimension 768", message)
                self.assertIn("actual 1024", message)
                self.assertIn("Qdrant 400", message)
                self.assertIn("expected dim: 768, got 1024", message)

        asyncio.run(run())

    def test_collection_creation_uses_settings_embedding_dimensions(self) -> None:
        service = QdrantService()
        fake_client = FakeAsyncClient(
            get_response=FakeResponse(404),
            put_response=FakeResponse(200),
        )

        async def run() -> None:
            from unittest.mock import patch

            with patch.object(settings, "embedding_dimensions", 1024):
                with patch("apps.api.app.services.qdrant.httpx.AsyncClient", return_value=fake_client):
                    await service.ensure_collection(settings.embedding_dimensions)

        asyncio.run(run())
        self.assertEqual(fake_client.put_calls[0]["vectors"]["size"], 1024)

    def test_delete_document_vectors_uses_scoped_filter(self) -> None:
        service = QdrantService()
        fake_client = FakeAsyncClient(put_response=FakeResponse(200, json_data={"result": "ok"}))
        document_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        async def run() -> None:
            from unittest.mock import patch

            with patch("apps.api.app.services.qdrant.httpx.AsyncClient", return_value=fake_client):
                await service.delete_document_vectors(document_id, workspace_id, user_id)

        asyncio.run(run())
        must = fake_client.post_calls[0]["filter"]["must"]
        self.assertIn({"key": "document_id", "match": {"value": str(document_id)}}, must)
        self.assertIn({"key": "workspace_id", "match": {"value": str(workspace_id)}}, must)
        self.assertIn({"key": "user_id", "match": {"value": str(user_id)}}, must)


if __name__ == "__main__":
    unittest.main()
