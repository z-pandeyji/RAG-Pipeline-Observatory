import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text

from apps.api.app.db.models import Base, Workspace
from apps.api.app.db.session import engine

DEFAULT_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OPENAPI_EXAMPLE_WORKSPACE_ID = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
DEFAULT_WORKSPACE_NAME = "Local Workspace"
OPENAPI_EXAMPLE_WORKSPACE_NAME = "API Docs Workspace"


async def init_db(db_engine: AsyncEngine = engine) -> None:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            pg_insert(Workspace)
            .values(
                [
                    {"id": DEFAULT_WORKSPACE_ID, "name": DEFAULT_WORKSPACE_NAME},
                    {
                        "id": OPENAPI_EXAMPLE_WORKSPACE_ID,
                        "name": OPENAPI_EXAMPLE_WORKSPACE_NAME,
                    },
                ]
            )
            .on_conflict_do_nothing(index_elements=[Workspace.id])
        )
        await _add_local_quiz_job_columns(connection)


async def _add_local_quiz_job_columns(connection) -> None:
    statements = [
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS prompt_text TEXT",
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS extracted_json TEXT",
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS fallback_used BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE quiz_generation_jobs ADD COLUMN IF NOT EXISTS timings JSONB NOT NULL DEFAULT '{}'::jsonb",
    ]
    for statement in statements:
        await connection.execute(text(statement))
