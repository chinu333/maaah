"""MCP tool-listing and tool-calling HTTP endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.mcp.server import mcp_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Request / Response models ────────────────────────────────────────────────


class ToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to invoke.")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    result: Any = None
    error: str | None = None


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools():
    """Return all available MCP tool definitions."""
    return mcp_server.list_tools()


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(req: ToolCallRequest):
    """Invoke an MCP tool by name."""
    try:
        resp = await mcp_server.call_tool(req.tool_name, req.arguments)
        if "error" in resp:
            raise HTTPException(status_code=400, detail=resp["error"])
        return ToolCallResponse(result=resp.get("result"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("MCP call_tool error")
        raise HTTPException(status_code=500, detail=str(exc))
