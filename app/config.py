from dataclasses import dataclass


@dataclass
class Settings:
    blob_storage_dir: str = "/tmp/secure-rag-learning/blobs"


settings = Settings()
