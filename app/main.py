"""MAAAH – FastAPI application entry point.

Registers all routers, mounts static files, sets up CORS, logging,
LangSmith tracing, and ensures the data directory exists.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, ensure_data_dir
from app.routes import chat, upload, health, mcp_routes
from app.utils.tracing import setup_tracing

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle logic."""
    # Startup
    settings = get_settings()
    ensure_data_dir()
    setup_tracing()

    logger.info(
        "MAAAH started – Azure OpenAI endpoint=%s, deployment=%s, data_dir=%s",
        settings.azure_openai_endpoint,
        settings.azure_openai_chat_deployment,
        settings.data_dir,
    )
    yield
    # Shutdown
    logger.info("MAAAH shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MAAAH – Multi Agent App – Atlanta Hub",
    version="1.0.0",
    description="Production multi-agent application powered by LangChain, LangGraph, and MCP.",
    lifespan=lifespan,
)

# CORS – allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(mcp_routes.router, prefix="/api")

# Static files
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Serve the SPA index.html on the root path
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "MAAAH API is running. Place static/index.html for the UI."})


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred.", "error": str(exc)},
    )
