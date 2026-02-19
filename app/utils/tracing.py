"""LangSmith tracing configuration.

Call ``setup_tracing()`` during application startup to enable LangSmith
observability for all LangChain / LangGraph operations.
"""

from __future__ import annotations

import logging
import os

from app.config import get_settings

logger = logging.getLogger(__name__)


def setup_tracing() -> None:
    """Configure environment variables so LangSmith tracing is active."""
    settings = get_settings()

    if not settings.langsmith_api_key:
        logger.warning(
            "LANGSMITH_API_KEY is not set – tracing will be disabled."
        )
        return

    os.environ.setdefault("LANGCHAIN_TRACING_V2", str(settings.langchain_tracing_v2).lower())
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)

    logger.info(
        "LangSmith tracing enabled (project=%s, v2=%s)",
        settings.langchain_project,
        settings.langchain_tracing_v2,
    )
