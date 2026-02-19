"""Chat endpoint – the main interaction route for the frontend."""

import logging

from fastapi import APIRouter, HTTPException

from app.models import ChatRequest, ChatResponse, ErrorResponse
from app.graph.workflow import run_workflow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={500: {"model": ErrorResponse}},
)
async def chat(req: ChatRequest):
    """Process a user message by auto-routing to the best agent(s)."""
    try:
        result = await run_workflow(
            query=req.message,
            file_path=req.file_path,
            session_id=req.session_id,
        )
        agents_called = result["agents_called"]
        return ChatResponse(
            reply=result["response"],
            agent=agents_called[0] if agents_called else "general",
            agents_called=agents_called,
            session_id=req.session_id,
        )
    except Exception as exc:
        logger.exception("Chat endpoint error")
        raise HTTPException(status_code=500, detail=str(exc))
