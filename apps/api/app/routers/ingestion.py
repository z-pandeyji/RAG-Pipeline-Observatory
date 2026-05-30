from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.session import get_session
from apps.api.app.schemas.ingestion import IngestionResponse
from apps.api.app.services.ingestion import IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/documents/pdf", response_model=IngestionResponse)
async def upload_pdf(
    workspace_id: UUID = Form(...),
    user_id: UUID = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IngestionResponse:
    try:
        document_id, tool_run_id = await IngestionService(session).upload_pdf(
            workspace_id,
            user_id,
            file,
        )
    except ValueError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.commit()
        raise HTTPException(status_code=500, detail="PDF upload failed unexpectedly.") from exc
    await session.commit()
    return IngestionResponse(
        document_id=document_id,
        workspace_id=workspace_id,
        user_id=user_id,
        filename=file.filename,
        source_type="pdf",
        status="uploaded",
        tool_run_id=tool_run_id,
    )
