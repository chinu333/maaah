"""File upload endpoint."""

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.models import UploadResponse
from app.utils.file_utils import save_upload

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and store it in the data/ directory."""
    try:
        dest = await save_upload(file)
        return UploadResponse(
            filename=file.filename or "unknown",
            saved_path=str(dest),
            size_bytes=dest.stat().st_size,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")
