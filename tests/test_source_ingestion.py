import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from apps.api.app.db.models import SourceType
from apps.api.app.services.citations import CitationService
from apps.api.app.services.image_extraction import ImageValidationService
from apps.api.app.services.ingestion import IngestionService
from apps.api.app.services.ocr.base import OCRBlock, OCRResult
from apps.api.app.services.qdrant import QdrantService
from apps.api.app.services.youtube import (
    TranscriptSegment,
    YouTubeAudioDownloadError,
    YouTubeAudioFallbackDisabledError,
    YouTubeSource,
    YouTubeTranscriptUnavailableError,
    YouTubeURLValidator,
)


class FakeDocumentService:
    def __init__(self) -> None:
        self.created = []

    async def create_upload(
        self,
        workspace_id,
        user_id,
        filename,
        source_type,
        content_hash,
        blob_uri,
    ):
        document = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            filename=filename,
            source_type=source_type,
            content_hash=content_hash,
            blob_uri=blob_uri,
            status=None,
        )
        self.created.append(document)
        return document

    async def update_status(self, document, status, page_count=None, error_message=None):
        document.status = status
        document.error_message = error_message
        return document


class FakeToolRuns:
    def __init__(self) -> None:
        self.started = []
        self.succeeded = []
        self.failed = []

    async def start(self, workspace_id, user_id, tool_name, input_):
        run = SimpleNamespace(id=uuid4(), tool_name=tool_name, input=input_)
        self.started.append(tool_name)
        return run

    async def finish_success(self, run, output):
        run.output = output
        self.succeeded.append(run.tool_name)
        return run

    async def finish_failure(self, run, error):
        run.error = error
        self.failed.append(run.tool_name)
        return run


class FakeUploadFile:
    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self, limit: int) -> bytes:
        return self._content


class MissingTranscriptService:
    async def extract(self, youtube_url: str, title: str | None = None):
        raise YouTubeTranscriptUnavailableError("No public transcript available.")


class FakeAudioDownloader:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.cleaned = []

    async def download_audio(self, youtube_url: str):
        if self.error:
            raise self.error
        return "/tmp/fake-audio.webm", {
            "temp_dir": "/tmp/fake-youtube-audio",
            "duration": 42,
            "video_id": "abc123XYZ_9",
        }

    def cleanup(self, path: str) -> None:
        self.cleaned.append(path)


class FakeTranscriptionProvider:
    async def transcribe(self, audio_path: str):
        return [
            TranscriptSegment(
                text="Fallback transcript text",
                timestamp_start=1.25,
                timestamp_end=4.5,
            )
        ]


class SourceIngestionTests(unittest.TestCase):
    def test_youtube_url_validation_rejects_non_youtube_urls(self) -> None:
        with self.assertRaises(ValueError):
            YouTubeURLValidator().validate("https://example.com/watch?v=abc123")

    def test_youtube_document_creation_stores_source_type(self) -> None:
        service = IngestionService(session=None)
        documents = FakeDocumentService()
        service.documents = documents
        service.tool_runs = FakeToolRuns()

        asyncio.run(
            service.create_youtube_document(
                uuid4(),
                uuid4(),
                "https://www.youtube.com/watch?v=abc123XYZ_9",
                "Lecture",
            )
        )

        self.assertEqual(documents.created[0].source_type, SourceType.youtube)

    def test_transcript_chunks_preserve_timestamps(self) -> None:
        service = IngestionService(session=None)
        source = YouTubeSource(
            video_id="abc123XYZ_9",
            original_url="https://youtu.be/abc123XYZ_9",
            title="Lecture",
            segments=[TranscriptSegment("Segment text", 10.0, 14.5)],
        )
        unit = service._youtube_unit(source, source.segments[0])

        self.assertEqual(unit.timestamp_start, 10.0)
        self.assertEqual(unit.timestamp_end, 14.5)
        self.assertEqual(unit.metadata["video_id"], "abc123XYZ_9")

    def test_youtube_short_segments_are_merged_into_useful_chunks(self) -> None:
        service = IngestionService(session=None)
        source = YouTubeSource(
            video_id="abc123XYZ_9",
            original_url="https://youtu.be/abc123XYZ_9",
            title="Lecture",
            segments=[
                TranscriptSegment("This lesson explains registration requirements.", 0.0, 2.0),
                TranscriptSegment("The certificate contains enterprise details.", 2.0, 4.0),
                TranscriptSegment("Applicants should verify official information carefully.", 4.0, 6.0),
            ],
        )

        chunks = service._youtube_units(source)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].timestamp_start, 0.0)
        self.assertEqual(chunks[0].timestamp_end, 6.0)
        self.assertIn("registration requirements", chunks[0].text)
        self.assertIn("enterprise details", chunks[0].text)

    def test_youtube_filler_segments_are_skipped_when_merging(self) -> None:
        service = IngestionService(session=None)
        source = YouTubeSource(
            video_id="abc123XYZ_9",
            original_url="https://youtu.be/abc123XYZ_9",
            title="Lecture",
            segments=[
                TranscriptSegment("I made a mistake", 0.0, 1.0),
                TranscriptSegment("Okay", 1.0, 2.0),
                TranscriptSegment(
                    "This meaningful segment explains the actual source content for study.",
                    2.0,
                    5.0,
                ),
            ],
        )

        chunks = service._youtube_units(source)

        self.assertEqual(len(chunks), 1)
        self.assertNotIn("I made a mistake", chunks[0].text)
        self.assertNotIn("Okay", chunks[0].text)
        self.assertIn("meaningful segment", chunks[0].text)

    def test_youtube_qdrant_payload_includes_scope_video_and_timestamps(self) -> None:
        workspace_id = uuid4()
        user_id = uuid4()
        payload = QdrantService().chunk_payload(
            uuid4(),
            uuid4(),
            workspace_id,
            user_id,
            "youtube",
            None,
            0,
            {
                "video_id": "abc123XYZ_9",
                "timestamp_start": 10.0,
                "timestamp_end": 14.5,
            },
        )

        self.assertEqual(payload["workspace_id"], str(workspace_id))
        self.assertEqual(payload["user_id"], str(user_id))
        self.assertEqual(payload["video_id"], "abc123XYZ_9")
        self.assertEqual(payload["timestamp_start"], 10.0)

    def test_youtube_citations_include_timestamp_fields(self) -> None:
        chunk = SimpleNamespace(
            document_id=uuid4(),
            id=uuid4(),
            page_number=None,
            timestamp="10.0-14.5",
            source_type=SourceType.youtube,
            text="Transcript text",
            metadata_={
                "timestamp_start": 10.0,
                "timestamp_end": 14.5,
                "youtube_url": "https://youtu.be/abc123XYZ_9",
                "video_id": "abc123XYZ_9",
            },
        )

        citation = CitationService().from_chunk(chunk)

        self.assertEqual(citation.timestamp_start, 10.0)
        self.assertEqual(citation.timestamp_end, 14.5)
        self.assertEqual(citation.url, "https://youtu.be/abc123XYZ_9")
        self.assertEqual(citation.metadata["video_id"], "abc123XYZ_9")

    def test_youtube_transcript_missing_raises_dedicated_error(self) -> None:
        service = IngestionService(session=None)
        service.youtube_transcripts._extract_public_transcript = lambda video_id: []

        with self.assertRaises(YouTubeTranscriptUnavailableError) as context:
            asyncio.run(
                service.youtube_transcripts.extract(
                    "https://www.youtube.com/watch?v=bMTlNeKqV4o",
                    "Lecture",
                )
            )

        self.assertIn("No public transcript extractor configured", str(context.exception))

    def test_public_transcript_unavailable_triggers_audio_fallback_when_enabled(self) -> None:
        service = IngestionService(
            session=None,
            transcription_provider=FakeTranscriptionProvider(),
            youtube_audio_downloader=FakeAudioDownloader(),
        )
        tool_runs = FakeToolRuns()
        service.tool_runs = tool_runs
        service.youtube_transcripts = MissingTranscriptService()
        document = SimpleNamespace(
            id=uuid4(),
            filename="Lecture",
            blob_uri="https://www.youtube.com/watch?v=abc123XYZ_9",
            source_type=SourceType.youtube,
        )

        with patch("apps.api.app.services.ingestion.settings.youtube_audio_fallback_enabled", True):
            chunks, page_count = asyncio.run(service._extract_youtube(document, uuid4(), uuid4()))

        self.assertEqual(page_count, 0)
        self.assertEqual(chunks[0].text, "Fallback transcript text")
        self.assertEqual(chunks[0].timestamp_start, 1.25)
        self.assertIn("youtube_audio_download", tool_runs.started)
        self.assertIn("youtube_audio_transcription", tool_runs.started)

    def test_public_transcript_unavailable_returns_clear_error_when_fallback_disabled(self) -> None:
        service = IngestionService(
            session=None,
            transcription_provider=FakeTranscriptionProvider(),
            youtube_audio_downloader=FakeAudioDownloader(),
        )
        service.tool_runs = FakeToolRuns()
        service.youtube_transcripts = MissingTranscriptService()
        document = SimpleNamespace(
            id=uuid4(),
            filename="Lecture",
            blob_uri="https://www.youtube.com/watch?v=abc123XYZ_9",
            source_type=SourceType.youtube,
        )

        with patch("apps.api.app.services.ingestion.settings.youtube_audio_fallback_enabled", False):
            with self.assertRaises(YouTubeAudioFallbackDisabledError) as context:
                asyncio.run(service._extract_youtube(document, uuid4(), uuid4()))

        self.assertIn("Audio transcription fallback is required", str(context.exception))

    def test_ytdlp_failure_returns_clear_error(self) -> None:
        service = IngestionService(
            session=None,
            transcription_provider=FakeTranscriptionProvider(),
            youtube_audio_downloader=FakeAudioDownloader(
                YouTubeAudioDownloadError(
                    "yt-dlp is not installed. Install it with: pip install yt-dlp"
                )
            ),
        )
        service.tool_runs = FakeToolRuns()
        service.youtube_transcripts = MissingTranscriptService()
        document = SimpleNamespace(
            id=uuid4(),
            filename="Lecture",
            blob_uri="https://www.youtube.com/watch?v=abc123XYZ_9",
            source_type=SourceType.youtube,
        )

        with patch("apps.api.app.services.ingestion.settings.youtube_audio_fallback_enabled", True):
            with self.assertRaises(YouTubeAudioDownloadError) as context:
                asyncio.run(service._extract_youtube(document, uuid4(), uuid4()))

        self.assertIn("yt-dlp is not installed", str(context.exception))

    def test_transcription_segments_preserve_timestamps(self) -> None:
        segment = asyncio.run(FakeTranscriptionProvider().transcribe("/tmp/audio.webm"))[0]

        self.assertEqual(segment.timestamp_start, 1.25)
        self.assertEqual(segment.timestamp_end, 4.5)

    def test_image_upload_rejects_unsafe_file_types(self) -> None:
        with self.assertRaises(ValueError):
            ImageValidationService().validate("bad.gif", "image/gif", b"GIF89a")

    def test_image_document_creation_stores_source_type(self) -> None:
        service = IngestionService(session=None)
        documents = FakeDocumentService()
        service.documents = documents
        service.tool_runs = FakeToolRuns()
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (1).to_bytes(4, "big") + (1).to_bytes(4, "big")
        file = FakeUploadFile("diagram.png", "image/png", png)

        asyncio.run(service.upload_image(uuid4(), uuid4(), file, "Diagram"))

        self.assertEqual(documents.created[0].source_type, SourceType.image)

    def test_ocr_chunks_preserve_image_metadata(self) -> None:
        service = IngestionService(session=None)
        source = SimpleNamespace(
            filename="diagram.png",
            width=640,
            height=480,
            ocr=OCRResult(
                text="OCR text",
                blocks=[OCRBlock(text="OCR block", region={"x": 1, "y": 2, "w": 3, "h": 4})],
            ),
        )

        units = service._image_units(source)

        self.assertEqual(units[0].metadata["filename"], "diagram.png")
        self.assertEqual(units[0].metadata["width"], 640)
        self.assertEqual(units[0].image_region, {"x": 1, "y": 2, "w": 3, "h": 4})

    def test_image_qdrant_payload_includes_scope_and_image_metadata(self) -> None:
        workspace_id = uuid4()
        user_id = uuid4()
        payload = QdrantService().chunk_payload(
            uuid4(),
            uuid4(),
            workspace_id,
            user_id,
            "image",
            None,
            1,
            {"filename": "diagram.png", "width": 640, "height": 480},
        )

        self.assertEqual(payload["workspace_id"], str(workspace_id))
        self.assertEqual(payload["user_id"], str(user_id))
        self.assertEqual(payload["filename"], "diagram.png")
        self.assertEqual(payload["width"], 640)

    def test_image_citations_include_image_metadata(self) -> None:
        chunk = SimpleNamespace(
            document_id=uuid4(),
            id=uuid4(),
            page_number=None,
            timestamp=None,
            source_type=SourceType.image,
            text="OCR text",
            metadata_={"filename": "diagram.png", "image_region": {"x": 1}},
        )

        citation = CitationService().from_chunk(chunk)

        self.assertEqual(citation.image_region, {"x": 1})
        self.assertEqual(citation.metadata["filename"], "diagram.png")


if __name__ == "__main__":
    unittest.main()
