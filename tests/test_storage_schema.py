import unittest
from tempfile import TemporaryDirectory
from importlib import resources

from app.config import settings
from app.store import PostgresDocumentStore


class PostgresSchemaTests(unittest.TestCase):
    def test_schema_enables_pgvector_and_tenant_scoped_chunk_indexes(self) -> None:
        schema = resources.files("app.storage").joinpath("schema.sql").read_text()

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", schema)
        self.assertIn("embedding vector(768)", schema)
        self.assertIn("chunks_embedding_hnsw_idx", schema)
        self.assertIn("chunks_tenant_document_idx", schema)

    def test_blob_storage_writes_pdf_by_content_hash(self) -> None:
        original_dir = settings.blob_storage_dir
        try:
            with TemporaryDirectory() as temp_dir:
                settings.blob_storage_dir = temp_dir
                store = PostgresDocumentStore("postgresql://user:pass@127.0.0.1/db")
                blob_uri = store._write_blob("abcdef123456", b"%PDF-test")

                self.assertTrue(blob_uri.endswith("ab/abcdef123456.pdf"))
                with open(blob_uri, "rb") as blob:
                    self.assertEqual(blob.read(), b"%PDF-test")
        finally:
            settings.blob_storage_dir = original_dir


if __name__ == "__main__":
    unittest.main()
