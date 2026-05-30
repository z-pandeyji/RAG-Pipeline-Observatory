import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from apps.api.app.core.config import settings


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


class YouTubeTranscriptUnavailableError(ValueError):
    pass


class YouTubeAudioFallbackDisabledError(ValueError):
    pass


class YouTubeAudioDownloadError(ValueError):
    pass


class YouTubeVideoTooLongError(ValueError):
    pass


class TranscriptionUnavailableError(ValueError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    timestamp_start: float
    timestamp_end: float


@dataclass(frozen=True)
class YouTubeSource:
    video_id: str
    original_url: str
    title: str | None
    segments: list[TranscriptSegment]


class YouTubeURLValidator:
    def validate(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if parsed.scheme not in {"https", "http"} or host not in YOUTUBE_HOSTS:
            raise ValueError("Only YouTube URLs are supported.")
        if host == "youtu.be":
            video_id = parsed.path.strip("/")
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if not video_id and parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/")[2]
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):
            raise ValueError("YouTube URL does not include a valid video id.")
        return video_id


class YouTubeTranscriptService:
    def __init__(self, validator: YouTubeURLValidator | None = None) -> None:
        self.validator = validator or YouTubeURLValidator()

    async def extract(self, youtube_url: str, title: str | None = None) -> YouTubeSource:
        video_id = self.validator.validate(youtube_url)
        segments = self._extract_public_transcript(video_id)
        if segments:
            return YouTubeSource(
                video_id=video_id,
                original_url=youtube_url,
                title=title,
                segments=segments,
            )
        raise YouTubeTranscriptUnavailableError(
            f"No public transcript extractor configured for video {video_id}. "
            "Future audio transcription should implement this interface."
        )

    def _extract_public_transcript(self, video_id: str) -> list[TranscriptSegment]:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return []
        try:
            api = YouTubeTranscriptApi()
            if hasattr(api, "fetch"):
                raw_segments = api.fetch(video_id)
            else:
                raw_segments = YouTubeTranscriptApi.get_transcript(video_id)
        except Exception:
            return []
        return [
            TranscriptSegment(
                text=self._segment_value(item, "text"),
                timestamp_start=float(self._segment_value(item, "start")),
                timestamp_end=float(self._segment_value(item, "start"))
                + float(self._segment_value(item, "duration", 0.0)),
            )
            for item in raw_segments
            if self._segment_value(item, "text", "")
        ]

    def _segment_value(self, segment, key: str, default=None):
        if isinstance(segment, dict):
            return segment.get(key, default)
        return getattr(segment, key, default)


class YouTubeAudioDownloader:
    def __init__(self, validator: YouTubeURLValidator | None = None) -> None:
        self.validator = validator or YouTubeURLValidator()

    async def download_audio(self, youtube_url: str) -> tuple[str, dict]:
        video_id = self.validator.validate(youtube_url)
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise YouTubeAudioDownloadError(
                "yt-dlp is not installed. Install it with: pip install yt-dlp"
            ) from exc

        temp_dir = tempfile.mkdtemp(prefix="youtube-audio-")
        output_template = str(Path(temp_dir).joinpath("%(id)s.%(ext)s"))
        options = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with YoutubeDL(options) as ydl:
                preflight_info = ydl.extract_info(youtube_url, download=False)
                self._validate_download_info(preflight_info, video_id)
                info = ydl.extract_info(youtube_url, download=True)
        except Exception as exc:
            self.cleanup(temp_dir)
            if isinstance(exc, (YouTubeAudioDownloadError, YouTubeVideoTooLongError)):
                raise
            raise YouTubeAudioDownloadError(f"YouTube audio download failed: {exc}") from exc

        self._validate_download_info(info, video_id)
        duration = info.get("duration")

        audio_path = self._downloaded_path(info)
        if audio_path is None or not Path(audio_path).exists():
            self.cleanup(temp_dir)
            raise YouTubeAudioDownloadError("yt-dlp did not produce an audio file.")
        return audio_path, {"temp_dir": temp_dir, "duration": duration, "video_id": video_id}

    def _validate_download_info(self, info: dict, video_id: str) -> None:
        duration = info.get("duration")
        if duration is not None and float(duration) > settings.youtube_max_duration_seconds:
            raise YouTubeVideoTooLongError(
                f"YouTube video is too long for local transcription. "
                f"Max duration is {settings.youtube_max_duration_seconds} seconds."
            )
        if info.get("id") != video_id:
            raise YouTubeAudioDownloadError("Downloaded video id did not match the validated URL.")

    def cleanup(self, path: str) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=True)

    def _downloaded_path(self, info: dict) -> str | None:
        requested = info.get("requested_downloads") or []
        for item in requested:
            filepath = item.get("filepath")
            if filepath:
                return filepath
        filepath = info.get("filepath") or info.get("_filename")
        return filepath if isinstance(filepath, str) else None


class TranscriptionProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> list[TranscriptSegment]:
        raise NotImplementedError


class LocalWhisperTranscriptionProvider(TranscriptionProvider):
    async def transcribe(self, audio_path: str) -> list[TranscriptSegment]:
        segments = self._transcribe_with_faster_whisper(audio_path)
        if segments:
            return segments
        segments = self._transcribe_with_openai_whisper(audio_path)
        if segments:
            return segments
        raise TranscriptionUnavailableError(
            "Audio transcription fallback is unavailable. Install yt-dlp and faster-whisper, "
            "then enable YOUTUBE_AUDIO_FALLBACK_ENABLED=true. macOS also requires: brew install ffmpeg"
        )

    def _transcribe_with_faster_whisper(self, audio_path: str) -> list[TranscriptSegment]:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return []
        model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        raw_segments, _ = model.transcribe(audio_path)
        return [
            TranscriptSegment(
                text=segment.text.strip(),
                timestamp_start=float(segment.start),
                timestamp_end=float(segment.end),
            )
            for segment in raw_segments
            if segment.text.strip()
        ]

    def _transcribe_with_openai_whisper(self, audio_path: str) -> list[TranscriptSegment]:
        try:
            import whisper
        except ImportError:
            return []
        model = whisper.load_model(settings.whisper_model)
        result = model.transcribe(audio_path)
        raw_segments = result.get("segments") or []
        if raw_segments:
            return [
                TranscriptSegment(
                    text=str(segment.get("text", "")).strip(),
                    timestamp_start=float(segment.get("start", 0.0)),
                    timestamp_end=float(segment.get("end", segment.get("start", 0.0))),
                )
                for segment in raw_segments
                if str(segment.get("text", "")).strip()
            ]
        text = str(result.get("text", "")).strip()
        if not text:
            return []
        return [TranscriptSegment(text=text, timestamp_start=0.0, timestamp_end=0.0)]


def get_transcription_provider() -> TranscriptionProvider:
    if settings.transcription_provider != "local_whisper":
        raise TranscriptionUnavailableError(
            f"Unsupported transcription provider: {settings.transcription_provider}"
        )
    return LocalWhisperTranscriptionProvider()
