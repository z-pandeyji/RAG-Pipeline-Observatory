from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.core.config import settings
from apps.api.app.db.init_db import init_db
from apps.api.app.routers import citations, documents, generation, ingestion, quizzes, retrieval, system
from apps.api.app.routers import tool_runs

app = FastAPI(title=settings.app_name, version="0.1.0")



app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

app.include_router(documents.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(retrieval.router, prefix="/api")
app.include_router(generation.router, prefix="/api")
app.include_router(quizzes.router, prefix="/api")
app.include_router(citations.router, prefix="/api")
app.include_router(tool_runs.router, prefix="/api")
app.include_router(system.router, prefix="/api")


@app.on_event("startup")
async def startup() -> None:
    if settings.auto_create_tables:
        await init_db()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
