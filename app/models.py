"""Pydantic request / response models used across the application."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Agent names ──────────────────────────────────────────────────────────────

class AgentName(str, Enum):
    RAG = "rag"
    MULTIMODAL = "multimodal"
    NASA = "nasa"
    WEATHER = "weather"
    TRAFFIC = "traffic"
    SQL = "sql"
    VIZ = "viz"
    CICP = "cicp"
    IDA = "ida"
    GENERAL = "general"


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    agent: Optional[AgentName] = Field(None, description="Target agent (auto-detected if omitted)")
    session_id: str = Field(default="default", description="Chat session identifier")
    file_path: Optional[str] = Field(None, description="Path to an uploaded file for context")


class ChatResponse(BaseModel):
    """Response returned to the frontend."""
    reply: str
    agent: str
    agents_called: list[str] = Field(default_factory=list)
    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Upload ───────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Metadata returned after a successful file upload."""
    filename: str
    saved_path: str
    size_bytes: int
    content_type: str


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    agents: list[str] = [a.value for a in AgentName]


# ── Error ────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str
    code: int = 500
