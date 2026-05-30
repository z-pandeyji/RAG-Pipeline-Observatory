from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.core.config import settings
from apps.api.app.repositories.documents import DocumentRepository
from apps.api.app.repositories.tool_runs import ToolRunRepository
from apps.api.app.schemas.documents import (
    DocumentChunkOut,
    DocumentDeleteResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentOut,
    DocumentStatusUpdate,
)
from apps.api.app.schemas.ingestion import IngestionResponse, YouTubeIngestionRequest
from apps.api.app.schemas.lab import (
    DatasetStats,
    DocumentRagTraceOut,
    EmbeddingSummary,
    PageStats,
    QdrantSummary,
    SecurityChecks,
)
from apps.api.app.schemas.tool_runs import ToolRunOut
from apps.api.app.services.qdrant import QdrantService
from apps.api.app.services.documents import DocumentService
from apps.api.app.services.ingestion import (
    DocumentNotFoundInWorkspaceError,
    EmbeddingProviderUnavailableError,
    IngestionService,
    MissingDocumentBlobError,
    QdrantUnavailableError,
    QdrantUpsertFailedError,
    UnsupportedSourceTypeError,
)
from apps.api.app.services.youtube import (
    TranscriptionUnavailableError,
    YouTubeAudioDownloadError,
    YouTubeAudioFallbackDisabledError,
    YouTubeTranscriptUnavailableError,
    YouTubeVideoTooLongError,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentListResponse:
    rows = await DocumentRepository(session).list_scoped_with_chunk_counts(workspace_id, user_id)
    return DocumentListResponse(
        documents=[
            DocumentListItem.model_validate(document).model_copy(
                update={"chunk_count": chunk_count}
            )
            for document, chunk_count in rows
        ]
    )


@router.post("/youtube", response_model=IngestionResponse)
async def create_youtube_document(
    request: YouTubeIngestionRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestionResponse:
    try:
        document_id, tool_run_id = await IngestionService(session).create_youtube_document(
            request.workspace_id,
            request.user_id,
            request.youtube_url,
            request.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return IngestionResponse(
        document_id=document_id,
        workspace_id=request.workspace_id,
        user_id=request.user_id,
        filename=request.title or request.youtube_url,
        source_type="youtube",
        status="uploaded",
        tool_run_id=tool_run_id,
    )


@router.post("/image", response_model=IngestionResponse)
async def create_image_document(
    workspace_id: UUID = Form(...),
    user_id: UUID = Form(...),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IngestionResponse:
    try:
        document_id, tool_run_id = await IngestionService(session).upload_image(
            workspace_id,
            user_id,
            file,
            title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return IngestionResponse(
        document_id=document_id,
        workspace_id=workspace_id,
        user_id=user_id,
        filename=title or file.filename,
        source_type="image",
        status="uploaded",
        tool_run_id=tool_run_id,
    )


@router.delete("/failed", response_model=DocumentDeleteResponse)
async def delete_failed_documents(
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentDeleteResponse:
    deleted_count = await DocumentService(session).delete_failed_documents(workspace_id, user_id)
    await session.commit()
    return DocumentDeleteResponse(
        deleted=True,
        deleted_count=deleted_count,
        message=f"Deleted {deleted_count} failed document(s).",
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    document = await DocumentRepository(session).get_scoped(document_id, workspace_id, user_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentOut.model_validate(document)


@router.post("/{document_id}/ingest", response_model=IngestionResponse)
async def ingest_document(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> IngestionResponse:
    try:
        tool_run_id = await IngestionService(session).process_document(
            document_id,
            workspace_id,
            user_id,
        )
    except DocumentNotFoundInWorkspaceError as exc:
        await session.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingDocumentBlobError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnsupportedSourceTypeError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except YouTubeTranscriptUnavailableError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except YouTubeAudioFallbackDisabledError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TranscriptionUnavailableError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except YouTubeAudioDownloadError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except YouTubeVideoTooLongError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingProviderUnavailableError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QdrantUnavailableError as exc:
        await session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QdrantUpsertFailedError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.commit()
        raise HTTPException(status_code=500, detail="Ingestion failed unexpectedly.") from exc
    await session.commit()
    document = await DocumentRepository(session).get_scoped(document_id, workspace_id, user_id)
    return IngestionResponse(
        document_id=document_id,
        workspace_id=workspace_id,
        user_id=user_id,
        filename=document.filename if document else None,
        source_type=document.source_type if document else None,
        status=document.status.value if document else "indexed",
        tool_run_id=tool_run_id,
    )


@router.get("/{document_id}/status", response_model=DocumentOut)
async def get_document_status(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    document = await DocumentRepository(session).get_scoped(document_id, workspace_id, user_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkOut])
async def list_document_chunks(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentChunkOut]:
    chunks = await DocumentRepository(session).list_chunks_scoped(
        document_id,
        workspace_id,
        user_id,
    )
    return [
        DocumentChunkOut(
            id=chunk.id,
            document_id=chunk.document_id,
            workspace_id=chunk.workspace_id,
            user_id=chunk.user_id,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            source_type=chunk.source_type,
            text=chunk.text,
            metadata=chunk.metadata_,
        )
        for chunk in chunks
    ]


@router.get("/{document_id}/rag-trace", response_model=DocumentRagTraceOut)
async def get_document_rag_trace(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentRagTraceOut:
    document_repository = DocumentRepository(session)
    document = await document_repository.get_scoped(document_id, workspace_id, user_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    chunks = await document_repository.list_chunks_scoped(document_id, workspace_id, user_id)
    chunk_out = [
        DocumentChunkOut(
            id=chunk.id,
            document_id=chunk.document_id,
            workspace_id=chunk.workspace_id,
            user_id=chunk.user_id,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            source_type=chunk.source_type,
            text=chunk.text,
            metadata=chunk.metadata_,
        )
        for chunk in chunks
    ]
    tool_runs = await ToolRunRepository(session).list_scoped(workspace_id, user_id)
    filtered_runs = [run for run in tool_runs if run.input.get("document_id") == str(document_id)]
    vector_count = _latest_count(filtered_runs, "qdrant_upsert", "points") or _latest_count(
        filtered_runs,
        "embedding_generation",
        "vectors",
    )
    page_stats = _page_stats(chunks)
    character_count = sum(len(chunk.text) for chunk in chunks)
    word_count = sum(len(chunk.text.split()) for chunk in chunks)
    return DocumentRagTraceOut(
        document=DocumentOut.model_validate(document),
        dataset_stats=DatasetStats(
            page_count=document.page_count or len(page_stats),
            character_count=character_count,
            word_count=word_count,
            chunk_count=len(chunks),
            avg_chunk_size=round(character_count / len(chunks)) if chunks else 0,
        ),
        pages=page_stats,
        chunks=chunk_out,
        embedding_summary=EmbeddingSummary(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            vector_count=vector_count,
            chunk_target_chars=settings.chunk_target_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
        ),
        qdrant_summary=QdrantSummary(
            collection=settings.qdrant_collection,
            vector_count=vector_count,
            filter=QdrantService().scope_filter(workspace_id, user_id, [document_id], "pdf"),
        ),
        security_checks=SecurityChecks(
            file_validation="PDF header and upload size are validated before storage.",
        ),
        tool_runs=[ToolRunOut.model_validate(run) for run in filtered_runs],
    )


def _latest_count(tool_runs, tool_name: str, key: str) -> int:
    for run in sorted(tool_runs, key=lambda item: item.created_at, reverse=True):
        if run.tool_name == tool_name:
            value = run.output.get(key)
            if isinstance(value, int):
                return value
    return 0


def _page_stats(chunks) -> list[PageStats]:
    pages: dict[int | None, dict[str, int]] = {}
    for chunk in chunks:
        page = chunk.page_number
        current = pages.setdefault(page, {"characters": 0, "words": 0, "chunks": 0})
        current["characters"] += len(chunk.text)
        current["words"] += len(chunk.text.split())
        current["chunks"] += 1
    return [
        PageStats(
            page_number=page,
            character_count=stats["characters"],
            word_count=stats["words"],
            chunk_count=stats["chunks"],
        )
        for page, stats in sorted(pages.items(), key=lambda item: item[0] or 0)
    ]


@router.get("/{document_id}/tool-runs", response_model=list[ToolRunOut])
async def list_document_tool_runs(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ToolRunOut]:
    runs = await ToolRunRepository(session).list_scoped(workspace_id, user_id)
    filtered = [run for run in runs if run.input.get("document_id") == str(document_id)]
    return [ToolRunOut.model_validate(run) for run in filtered]


@router.patch("/{document_id}/status", response_model=DocumentOut)
async def update_document_status(
    document_id: UUID,
    request: DocumentStatusUpdate,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    repository = DocumentRepository(session)
    document = await repository.get_scoped(document_id, workspace_id, user_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    updated = await DocumentService(session).update_status(
        document,
        request.status,
        page_count=request.page_count,
        error_message=request.error_message,
    )
    await session.commit()
    return DocumentOut.model_validate(updated)


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    workspace_id: UUID = Query(...),
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentDeleteResponse:
    try:
        await DocumentService(session).delete_document(document_id, workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return DocumentDeleteResponse(
        deleted=True,
        document_id=document_id,
        message="Document deleted.",
    )
