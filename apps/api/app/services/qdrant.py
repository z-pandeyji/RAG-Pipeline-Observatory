from uuid import UUID

from datetime import datetime
from enum import Enum
import re

import httpx

from apps.api.app.core.config import settings


class QdrantUnavailableError(RuntimeError):
    pass


class QdrantUpsertError(ValueError):
    pass


class QdrantService:
    def __init__(
        self,
        base_url: str = settings.qdrant_url,
        collection: str = settings.qdrant_collection,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection

    def scope_filter(
        self,
        workspace_id: UUID,
        user_id: UUID,
        document_ids: list[UUID],
        source_type: str | None = None,
    ) -> dict:
        must = [
            {"key": "workspace_id", "match": {"value": str(workspace_id)}},
            {"key": "user_id", "match": {"value": str(user_id)}},
        ]
        if document_ids:
            must.append(
                {
                    "key": "document_id",
                    "match": {"any": [str(document_id) for document_id in document_ids]},
                }
            )
        if source_type:
            must.append({"key": "source_type", "match": {"value": source_type}})
        return {"must": must}

    async def ensure_collection(self, vector_size: int) -> None:
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            try:
                response = await client.get(f"{self.base_url}/collections/{self.collection}")
                if response.status_code == 200:
                    collection_size = self._collection_vector_size(response.json())
                    if collection_size is not None and collection_size != vector_size:
                        raise QdrantUpsertError(
                            f"Qdrant collection '{self.collection}' expects vector dimension "
                            f"{collection_size}, but EMBEDDING_DIMENSIONS is {vector_size}."
                        )
                    return
                if response.status_code != 404:
                    response.raise_for_status()
                create_response = await client.put(
                    f"{self.base_url}/collections/{self.collection}",
                    json={"vectors": {"size": vector_size, "distance": "Cosine"}},
                )
                create_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 400:
                    collection_size, actual_vector_size = self._parse_dimension_error(exc.response.text)
                    raise self._build_upsert_error(
                        status_code=exc.response.status_code,
                        response_text=exc.response.text,
                        vector_size=vector_size,
                        actual_vector_size=actual_vector_size,
                        collection_vector_size=collection_size,
                    ) from exc
                raise QdrantUnavailableError("Qdrant service is unavailable.") from exc
            except httpx.HTTPError as exc:
                raise QdrantUnavailableError("Qdrant service is unavailable.") from exc

    async def upsert_chunk(
        self,
        point_id: UUID,
        vector: list[float],
        payload: dict,
    ) -> None:
        await self.upsert_chunks([(point_id, vector, payload)])

    async def upsert_chunks(self, points: list[tuple[UUID, list[float], dict]]) -> None:
        if not points:
            return
        prepared = self._prepare_points(points)
        body = {"points": prepared}
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            try:
                response = await client.put(
                    f"{self.base_url}/collections/{self.collection}/points",
                    json=body,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                actual_vector_size = len(prepared[0]["vector"]) if prepared else 0
                if exc.response.status_code == 400:
                    collection_size, parsed_actual_size = self._parse_dimension_error(exc.response.text)
                    raise self._build_upsert_error(
                        status_code=exc.response.status_code,
                        response_text=exc.response.text,
                        vector_size=settings.embedding_dimensions,
                        actual_vector_size=parsed_actual_size if parsed_actual_size else actual_vector_size,
                        collection_vector_size=collection_size,
                    ) from exc
                raise QdrantUnavailableError("Qdrant service is unavailable.") from exc
            except httpx.HTTPError as exc:
                raise QdrantUnavailableError("Qdrant service is unavailable.") from exc

    def chunk_payload(
        self,
        chunk_id: UUID,
        document_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        source_type: str,
        page_number: int | None,
        chunk_index: int,
        metadata: dict | None = None,
    ) -> dict:
        metadata = metadata or {}
        payload = self._json_safe(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "source_type": source_type,
                "page_number": page_number,
                "chunk_index": chunk_index,
                **{
                    key: value
                    for key, value in metadata.items()
                    if key
                    in {
                        "video_id",
                        "youtube_url",
                        "timestamp_start",
                        "timestamp_end",
                        "filename",
                        "width",
                        "height",
                        "image_region",
                    }
                },
            }
        )
        return payload

    async def search(
        self,
        vector: list[float],
        workspace_id: UUID,
        user_id: UUID,
        document_ids: list[UUID],
        limit: int,
        source_type: str | None = None,
    ) -> list[dict]:
        body = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "filter": self.scope_filter(workspace_id, user_id, document_ids, source_type),
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/collections/{self.collection}/points/search",
                json=body,
            )
            response.raise_for_status()
        return response.json().get("result", [])

    async def delete_document_vectors(
        self,
        document_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
    ) -> dict:
        body = {
            "filter": {
                "must": [
                    {"key": "document_id", "match": {"value": str(document_id)}},
                    {"key": "workspace_id", "match": {"value": str(workspace_id)}},
                    {"key": "user_id", "match": {"value": str(user_id)}},
                ]
            }
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/collections/{self.collection}/points/delete",
                    json=body,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise QdrantUnavailableError("Qdrant document vector cleanup failed.") from exc
        return response.json()

    def parse_search_results(self, results: list[dict]) -> list[tuple[UUID, float]]:
        parsed: list[tuple[UUID, float]] = []
        for result in results:
            payload = result.get("payload") or {}
            chunk_id = payload.get("chunk_id") or result.get("id")
            if chunk_id is None:
                continue
            parsed.append((UUID(str(chunk_id)), float(result.get("score", 0.0))))
        return parsed

    def _prepare_points(self, points: list[tuple[UUID, list[float], dict]]) -> list[dict]:
        prepared: list[dict] = []
        for point_id, vector, payload in points:
            normalized_vector = self._normalize_vector(vector)
            prepared.append(
                {
                    "id": str(point_id),
                    "vector": normalized_vector,
                    "payload": self._json_safe(payload),
                }
            )
        return prepared

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        if not isinstance(vector, list):
            vector = list(vector)
        if any(isinstance(item, (list, tuple, dict)) for item in vector):
            raise ValueError("Qdrant vectors must be a flat list of floats.")
        normalized = [float(item) for item in vector]
        actual_dimensions = len(normalized)
        expected_dimensions = settings.embedding_dimensions
        if actual_dimensions != expected_dimensions:
            raise ValueError(
                f"Embedding dimension mismatch: model returned {actual_dimensions} dimensions "
                f"but EMBEDDING_DIMENSIONS is {expected_dimensions}."
            )
        return normalized

    def _json_safe(self, value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        return value

    def _build_upsert_error(
        self,
        status_code: int,
        response_text: str,
        vector_size: int,
        actual_vector_size: int,
        collection_vector_size: int | None = None,
    ) -> QdrantUpsertError:
        response_detail = response_text.strip()
        expected_dimensions = collection_vector_size if collection_vector_size is not None else vector_size
        message = (
            f"Qdrant upsert failed for collection '{self.collection}' "
            f"(expected vector dimension {expected_dimensions}, actual {actual_vector_size})."
        )
        if response_detail:
            message = f"{message} Qdrant {status_code}: {response_detail}"
        else:
            message = f"{message} Qdrant {status_code}."
        return QdrantUpsertError(message)

    def _collection_vector_size(self, payload: dict) -> int | None:
        result = payload.get("result") or {}
        config = result.get("config") or {}
        params = config.get("params") or {}
        vectors = params.get("vectors")
        if isinstance(vectors, dict) and vectors.get("size") is not None:
            return int(vectors["size"])
        if isinstance(vectors, list) and vectors:
            first = vectors[0]
            if isinstance(first, dict) and first.get("size") is not None:
                return int(first["size"])
        if isinstance(vectors, int):
            return int(vectors)
        return None

    def _parse_dimension_error(self, response_text: str) -> tuple[int | None, int]:
        collection_dim = None
        actual_dim = settings.embedding_dimensions
        expected_match = re.search(r"expected dim:\s*(\d+)", response_text)
        got_match = re.search(r"got\s*(\d+)", response_text)
        if expected_match:
            collection_dim = int(expected_match.group(1))
        if got_match:
            actual_dim = int(got_match.group(1))
        return collection_dim, actual_dim
