"""Health-check and metadata endpoint."""

from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return application health status."""
    return HealthResponse()
