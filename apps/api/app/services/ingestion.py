from hashlib import sha256
from pathlib import Path
import re
from uuid import UUID

import httpx
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import settings
from apps.api.app.db.models import DocumentChunk, DocumentStatus, SourceType
from apps.api.app.repositories.documents import DocumentRepository
from apps.api.app.services.chunking import SemanticChunkingService
from apps.api.app.services.documents import DocumentService
from apps.api.app.services.embeddings.base import EmbeddingProvider, EmbeddingRequest
from apps.api.app.services.embeddings.factory import get_embedding_provider
from apps.api.app.services.image_extraction import ImageExtractionService, ImageValidationService
from apps.api.app.services.pdf_extraction import PdfExtractionService
from apps.api.app.services.qdrant import (
    QdrantService,
    QdrantUnavailableError as QdrantServiceUnavailableError,
    QdrantUpsertError as QdrantServiceUpsertError,
)
from apps.api.app.services.tool_runs import ToolRunLogger
from apps.api.app.services.youtube import YouTubeTranscriptService, YouTubeURLValidator
from apps.api.app.services.youtube import (
    TranscriptionProvider,
    YouTubeAudioDownloader,
    YouTubeAudioFallbackDisabledError,
    YouTubeTranscriptUnavailableError,
    get_transcription_provider,
)


class IngestionError(Exception):
    pass


class DocumentNotFoundInWorkspaceError(IngestionError):
    pass


class UnsupportedSourceTypeError(IngestionError):
    pass


class MissingDocumentBlobError(IngestionError):
    pass


class EmbeddingProviderUnavailableError(IngestionError):
    pass


class QdrantUnavailableError(IngestionError):
    pass


class QdrantUpsertFailedError(IngestionError):
    pass


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
        qdrant: QdrantService | None = None,
        transcription_provider: TranscriptionProvider | None = None,
        youtube_audio_downloader: YouTubeAudioDownloader | None = None,
    ) -> None:
        self.session = session
        self.documents = DocumentService(session)
        self.document_repository = DocumentRepository(session)
        self.tool_runs = ToolRunLogger(session)
        self.pdf_extractor = PdfExtractionService()
        self.chunker = SemanticChunkingService(
            target_chars=settings.chunk_target_chars,
            overlap_chars=settings.chunk_overlap_chars,
        )
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.qdrant = qdrant or QdrantService()
        self.youtube_validator = YouTubeURLValidator()
        self.youtube_transcripts = YouTubeTranscriptService(self.youtube_validator)
        self.youtube_audio_downloader = youtube_audio_downloader or YouTubeAudioDownloader(
            self.youtube_validator
        )
        self.transcription_provider = transcription_provider or get_transcription_provider()
        self.image_validator = ImageValidationService()
        self.image_extractor = ImageExtractionService()

    async def upload_pdf(
        self,
        workspace_id: UUID,
        user_id: UUID,
        file: UploadFile,
    ) -> tuple[UUID, UUID]:
        max_bytes = settings.max_upload_mb * 1024 * 1024
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError(f"PDF is larger than {settings.max_upload_mb} MB.")
        if not content.startswith(b"%PDF-"):
            raise ValueError("Upload must be a valid PDF file.")

        content_hash = sha256(content).hexdigest()
        blob_uri = self._write_blob(content_hash, content)
        document = await self.documents.create_upload(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=file.filename or "document.pdf",
            source_type=SourceType.pdf,
            content_hash=content_hash,
            blob_uri=blob_uri,
        )
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "ingest_pdf",
            {"document_id": str(document.id), "filename": document.filename},
        )
        await self.tool_runs.finish_success(run, {"status": document.status.value})
        return document.id, run.id

    async def create_youtube_document(
        self,
        workspace_id: UUID,
        user_id: UUID,
        youtube_url: str,
        title: str | None = None,
    ) -> tuple[UUID, UUID]:
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "youtube_url_validation",
            {"youtube_url": youtube_url},
        )
        try:
            video_id = self.youtube_validator.validate(youtube_url)
        except Exception as exc:
            await self.tool_runs.finish_failure(run, str(exc))
            raise
        document = await self.documents.create_upload(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=title or video_id,
            source_type=SourceType.youtube,
            content_hash=video_id,
            blob_uri=youtube_url,
        )
        await self.tool_runs.finish_success(
            run,
            {"document_id": str(document.id), "video_id": video_id},
        )
        return document.id, run.id

    async def upload_image(
        self,
        workspace_id: UUID,
        user_id: UUID,
        file: UploadFile,
        title: str | None = None,
    ) -> tuple[UUID, UUID]:
        content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"Image is larger than {settings.max_upload_mb} MB.")
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "image_validation",
            {"filename": file.filename, "content_type": file.content_type},
        )
        try:
            extension = self.image_validator.validate(
                file.filename or "image",
                file.content_type,
                content,
            )
        except Exception as exc:
            await self.tool_runs.finish_failure(run, str(exc))
            raise
        width, height = self.image_validator.dimensions(extension, content)
        content_hash = sha256(content).hexdigest()
        blob_uri = self._write_blob(content_hash, content, extension)
        document = await self.documents.create_upload(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=title or file.filename or f"image.{extension}",
            source_type=SourceType.image,
            content_hash=content_hash,
            blob_uri=blob_uri,
        )
        await self.tool_runs.finish_success(
            run,
            {"document_id": str(document.id), "width": width, "height": height},
        )
        return document.id, run.id

    async def process_document(self, document_id: UUID, workspace_id: UUID, user_id: UUID) -> UUID:
        document = await self.document_repository.get_scoped(document_id, workspace_id, user_id)
        if document is None:
            raise DocumentNotFoundInWorkspaceError("Document not found for this workspace/user.")
        if document.status == DocumentStatus.indexed:
            run = await self.tool_runs.start(
                workspace_id,
                user_id,
                "ingest_document",
                {"document_id": str(document.id), "idempotent": True},
            )
            await self.tool_runs.finish_success(run, {"status": document.status.value})
            return run.id

        try:
            await self.documents.update_status(document, DocumentStatus.processing)
            if not document.blob_uri:
                raise MissingDocumentBlobError("Document blob is missing.")
            text_chunks, page_count = await self._extract_and_chunk(document, workspace_id, user_id)
            db_chunks = [
                DocumentChunk(
                    document_id=document.id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    timestamp=self._timestamp_label(chunk),
                    source_type=document.source_type,
                    text=chunk.text,
                    token_estimate=max(1, len(chunk.text) // 4),
                    metadata_=self._chunk_metadata(chunk),
                )
                for chunk in text_chunks
            ]
            qdrant_run = await self._persist_embed_upsert(
                document,
                workspace_id,
                user_id,
                db_chunks,
            )
            await self.documents.update_status(
                document,
                DocumentStatus.indexed,
                page_count=page_count,
                error_message=None,
            )
            return qdrant_run.id
        except Exception as exc:
            await self.documents.update_status(
                document,
                DocumentStatus.failed,
                error_message=str(exc),
            )
            raise

    async def mark_indexed(
        self,
        document_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        chunks: list[DocumentChunk],
        page_count: int,
    ) -> None:
        document = await self.document_repository.get_scoped(
            document_id,
            workspace_id,
            user_id,
        )
        if document is None:
            raise ValueError("Document not found for this workspace/user.")
        await self.document_repository.replace_chunks(document, chunks)
        await self.documents.update_status(document, DocumentStatus.indexed, page_count=page_count)

    async def _extract_and_chunk(self, document, workspace_id: UUID, user_id: UUID):
        if document.source_type == SourceType.pdf:
            return await self._extract_pdf(document, workspace_id, user_id)
        if document.source_type == SourceType.youtube:
            return await self._extract_youtube(document, workspace_id, user_id)
        if document.source_type == SourceType.image:
            return await self._extract_image(document, workspace_id, user_id)
        raise UnsupportedSourceTypeError(f"Unsupported source type: {document.source_type}")

    async def _extract_pdf(self, document, workspace_id: UUID, user_id: UUID):
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "pdf_text_extraction",
            {"document_id": str(document.id)},
        )
        try:
            pages = self.pdf_extractor.extract_pages(document.blob_uri)
            chunks = self.chunker.chunk_pages(pages)
        except Exception as exc:
            await self.tool_runs.finish_failure(run, str(exc))
            raise
        await self.tool_runs.finish_success(run, {"pages": len(pages)})
        return await self._run_chunking_tool(
            document,
            workspace_id,
            user_id,
            chunks,
            len(pages),
        )

    async def _extract_youtube(self, document, workspace_id: UUID, user_id: UUID):
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "youtube_transcript_extraction",
            {"document_id": str(document.id), "youtube_url": document.blob_uri},
        )
        try:
            source = await self.youtube_transcripts.extract(document.blob_uri, document.filename)
        except YouTubeTranscriptUnavailableError as exc:
            if not settings.youtube_audio_fallback_enabled:
                await self.tool_runs.finish_failure(
                    run,
                    (
                        "Public transcript was not available. Audio transcription fallback is "
                        "required. Enable YOUTUBE_AUDIO_FALLBACK_ENABLED=true and install "
                        "yt-dlp faster-whisper."
                    ),
                )
                raise YouTubeAudioFallbackDisabledError(
                    "Public transcript was not available. Audio transcription fallback is required. "
                    "Install yt-dlp and faster-whisper, then enable "
                    "YOUTUBE_AUDIO_FALLBACK_ENABLED=true."
                ) from exc
            await self.tool_runs.finish_success(
                run,
                {"transcript_available": False, "fallback": "audio_transcription"},
            )
            source = await self._extract_youtube_audio_fallback(document, workspace_id, user_id)
        except Exception as exc:
            await self.tool_runs.finish_failure(run, str(exc))
            raise
        else:
            await self.tool_runs.finish_success(
                run,
                {
                    "transcript_available": True,
                    "segments": len(source.segments),
                    "video_id": source.video_id,
                },
            )
        units = self._youtube_units(source)
        return await self._run_chunking_tool(document, workspace_id, user_id, units, 0)

    async def _extract_youtube_audio_fallback(self, document, workspace_id: UUID, user_id: UUID):
        from apps.api.app.services.youtube import YouTubeSource

        download_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "youtube_audio_download",
            {"document_id": str(document.id), "youtube_url": document.blob_uri},
        )
        audio_path = None
        temp_dir = None
        try:
            audio_path, audio_info = await self.youtube_audio_downloader.download_audio(
                document.blob_uri
            )
            temp_dir = audio_info.get("temp_dir")
            await self.tool_runs.finish_success(
                download_run,
                {
                    "video_id": audio_info.get("video_id"),
                    "duration": audio_info.get("duration"),
                    "audio_downloaded": True,
                },
            )
        except Exception as exc:
            await self.tool_runs.finish_failure(download_run, str(exc))
            raise

        transcription_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "youtube_audio_transcription",
            {
                "document_id": str(document.id),
                "provider": settings.transcription_provider,
                "model": settings.whisper_model,
            },
        )
        try:
            segments = await self.transcription_provider.transcribe(audio_path)
            if not segments:
                raise ValueError("Audio transcription produced no text.")
        except Exception as exc:
            await self.tool_runs.finish_failure(transcription_run, str(exc))
            raise
        finally:
            if temp_dir:
                self.youtube_audio_downloader.cleanup(temp_dir)
        await self.tool_runs.finish_success(
            transcription_run,
            {"segments": len(segments), "provider": settings.transcription_provider},
        )
        video_id = self.youtube_validator.validate(document.blob_uri)
        return YouTubeSource(
            video_id=video_id,
            original_url=document.blob_uri,
            title=document.filename,
            segments=segments,
        )

    async def _extract_image(self, document, workspace_id: UUID, user_id: UUID):
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "image_ocr_extraction",
            {"document_id": str(document.id), "filename": document.filename},
        )
        try:
            source = await self.image_extractor.extract(
                document.blob_uri,
                document.filename,
                None,
                None,
            )
            units = self._image_units(source)
        except Exception as exc:
            await self.tool_runs.finish_failure(run, str(exc))
            raise
        await self.tool_runs.finish_success(
            run,
            {"blocks": len(units), "width": source.width, "height": source.height},
        )
        return await self._run_chunking_tool(document, workspace_id, user_id, units, 1)

    async def _run_chunking_tool(
        self,
        document,
        workspace_id: UUID,
        user_id: UUID,
        chunks,
        page_count: int,
    ):
        run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "semantic_chunking",
            {"document_id": str(document.id), "source_type": document.source_type.value},
        )
        await self.tool_runs.finish_success(run, {"chunks": len(chunks)})
        return chunks, page_count

    async def _persist_embed_upsert(self, document, workspace_id: UUID, user_id: UUID, db_chunks):
        await self.document_repository.replace_chunks(document, db_chunks)
        embedding_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "embedding_generation",
            {"document_id": str(document.id), "chunks": len(db_chunks)},
        )
        try:
            embedding_response = await self.embedding_provider.embed(
                EmbeddingRequest(
                    texts=[chunk.text for chunk in db_chunks],
                    model=settings.embedding_model,
                )
            )
            if len(embedding_response.vectors) != len(db_chunks):
                raise ValueError("Embedding provider returned a mismatched vector count.")
        except httpx.HTTPError as exc:
            await self.tool_runs.finish_failure(embedding_run, str(exc))
            raise EmbeddingProviderUnavailableError("Embedding provider is unavailable.") from exc
        except Exception as exc:
            await self.tool_runs.finish_failure(embedding_run, str(exc))
            raise
        await self.tool_runs.finish_success(
            embedding_run,
            {"vectors": len(embedding_response.vectors)},
        )
        qdrant_run = await self.tool_runs.start(
            workspace_id,
            user_id,
            "qdrant_upsert",
            {"document_id": str(document.id), "chunks": len(db_chunks)},
        )
        try:
            await self.qdrant.ensure_collection(settings.embedding_dimensions)
            points = [
                (
                    chunk.id,
                    vector,
                    self.qdrant.chunk_payload(
                        chunk.id,
                        document.id,
                        workspace_id,
                        user_id,
                        chunk.source_type.value,
                        chunk.page_number,
                        chunk.chunk_index,
                        chunk.metadata_,
                    ),
                )
                for chunk, vector in zip(db_chunks, embedding_response.vectors, strict=True)
            ]
            await self.qdrant.upsert_chunks(points)
        except QdrantServiceUpsertError as exc:
            await self.tool_runs.finish_failure(qdrant_run, str(exc))
            raise QdrantUpsertFailedError(str(exc)) from exc
        except QdrantServiceUnavailableError as exc:
            await self.tool_runs.finish_failure(qdrant_run, str(exc))
            raise QdrantUnavailableError(str(exc)) from exc
        except Exception as exc:
            await self.tool_runs.finish_failure(qdrant_run, str(exc))
            raise
        await self.tool_runs.finish_success(qdrant_run, {"points": len(points)})
        return qdrant_run

    def _youtube_unit(self, source, segment):
        from apps.api.app.services.chunking import TextChunk

        return TextChunk(
            text=segment.text,
            chunk_index=0,
            timestamp_start=segment.timestamp_start,
            timestamp_end=segment.timestamp_end,
            metadata={
                "video_id": source.video_id,
                "youtube_url": source.original_url,
                "title": source.title,
            },
        )

    def _youtube_units(self, source):
        if not settings.youtube_merge_segments:
            return [
                self.chunker._copy_chunk(
                    source=self._youtube_unit(source, segment),
                    text=segment.text,
                    index=index,
                )
                for index, segment in enumerate(source.segments)
                if self._is_useful_youtube_text(segment.text)
            ]
        return self._merge_youtube_segments(source)

    def _merge_youtube_segments(self, source):
        from apps.api.app.services.chunking import TextChunk

        chunks: list[TextChunk] = []
        rolling_text: list[str] = []
        start = None
        end = None
        metadata = {
            "video_id": source.video_id,
            "youtube_url": source.original_url,
            "title": source.title,
            "chunking": "youtube_timestamp_merge",
        }
        for segment in source.segments:
            text = " ".join(segment.text.split())
            if not text or self._is_filler_youtube_text(text):
                continue
            if start is None:
                start = segment.timestamp_start
            end = segment.timestamp_end
            rolling_text.append(text)
            joined = " ".join(rolling_text).strip()
            if len(joined) >= settings.youtube_target_chunk_chars:
                chunks.append(
                    TextChunk(
                        text=joined,
                        chunk_index=len(chunks),
                        timestamp_start=start,
                        timestamp_end=end,
                        metadata=metadata,
                    )
                )
                rolling_text = []
                start = None
                end = None
        if rolling_text:
            joined = " ".join(rolling_text).strip()
            if len(joined) >= settings.min_chunk_chars or not chunks:
                chunks.append(
                    TextChunk(
                        text=joined,
                        chunk_index=len(chunks),
                        timestamp_start=start,
                        timestamp_end=end,
                        metadata=metadata,
                    )
                )
            elif chunks:
                previous = chunks[-1]
                chunks[-1] = TextChunk(
                    text=f"{previous.text} {joined}".strip(),
                    chunk_index=previous.chunk_index,
                    timestamp_start=previous.timestamp_start,
                    timestamp_end=end or previous.timestamp_end,
                    metadata=previous.metadata,
                )
        return chunks

    def _is_useful_youtube_text(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        return len(normalized) >= settings.min_chunk_chars and not self._is_filler_youtube_text(normalized)

    def _is_filler_youtube_text(self, text: str) -> bool:
        normalized = re.sub(r"[^a-z0-9\s]", "", text.lower())
        normalized = " ".join(normalized.split())
        filler = {
            "i made a mistake",
            "okay",
            "ok",
            "yes",
            "yeah",
            "i understand",
            "i have understood",
            "thank you",
        }
        return normalized in filler

    def _image_units(self, source):
        from apps.api.app.services.chunking import TextChunk

        blocks = source.ocr.blocks or []
        if not blocks and source.ocr.text:
            blocks = [type("Block", (), {"text": source.ocr.text, "region": None})()]
        return [
            TextChunk(
                text=block.text,
                chunk_index=index,
                image_region=block.region,
                metadata={
                    "filename": source.filename,
                    "width": source.width,
                    "height": source.height,
                    "image_region": block.region,
                },
            )
            for index, block in enumerate(blocks)
        ]

    def _timestamp_label(self, chunk) -> str | None:
        if chunk.timestamp_start is None:
            return None
        return f"{chunk.timestamp_start}-{chunk.timestamp_end}"

    def _chunk_metadata(self, chunk) -> dict:
        metadata = dict(chunk.metadata)
        if chunk.timestamp_start is not None:
            metadata["timestamp_start"] = chunk.timestamp_start
            metadata["timestamp_end"] = chunk.timestamp_end
        if chunk.image_region is not None:
            metadata["image_region"] = chunk.image_region
        return metadata

    def _write_blob(self, content_hash: str, content: bytes, extension: str = "pdf") -> str:
        directory = Path(settings.app_name.replace(" ", "_").lower()).joinpath(
            "blobs",
            content_hash[:2],
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory.joinpath(f"{content_hash}.{extension}")
        if not path.exists():
            path.write_bytes(content)
        return path.as_posix()
