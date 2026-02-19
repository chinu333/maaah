"""File-handling utilities for uploads and data directory management."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings, ensure_data_dir

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: set[str] = {
    ".txt", ".md", ".pdf", ".csv", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".docx", ".xlsx",
}


def _safe_filename(original: str) -> str:
    """Generate a collision-free filename while keeping the original extension."""
    p = Path(original)
    stem = p.stem[:80].replace(" ", "_")
    return f"{stem}_{uuid.uuid4().hex[:8]}{p.suffix.lower()}"


async def save_upload(upload: UploadFile) -> Path:
    """Persist an uploaded file to the data directory and return its path."""
    data_dir = ensure_data_dir()
    settings = get_settings()

    ext = Path(upload.filename or "file.bin").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    content = await upload.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(
            f"File too large ({len(content) / 1024 / 1024:.1f} MB). "
            f"Max allowed: {settings.max_upload_size_mb} MB."
        )

    safe_name = _safe_filename(upload.filename or "file.bin")
    dest = data_dir / safe_name
    dest.write_bytes(content)
    logger.info("Saved upload: %s → %s (%d bytes)", upload.filename, dest, len(content))
    return dest
