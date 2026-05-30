from pathlib import Path

from app.config import settings


class PostgresDocumentStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _write_blob(self, content_hash: str, content: bytes) -> str:
        prefix = content_hash[:2]
        directory = Path(settings.blob_storage_dir) / prefix
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{content_hash}.pdf"
        path.write_bytes(content)
        return str(path)
