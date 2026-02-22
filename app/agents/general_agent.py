"""General LLM Agent — a capable chat assistant backed by Azure OpenAI.

Authentication uses **DefaultAzureCredential** (role-based access).

When a file is attached, the agent reads its text content and includes it
in the prompt so it can answer questions about the file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)

_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".xml", ".yaml", ".yml", ".log"}


async def invoke(query: str, *, file_path: Optional[str] = None, history: str = "", **kwargs) -> str:
    """Send the user's query to Azure OpenAI and return the response."""

    llm = get_chat_llm(temperature=0.7, name="general-agent-llm")

    # Build optional file context
    file_context = ""
    if file_path:
        path = Path(file_path)
        if path.exists() and path.suffix.lower() in _TEXT_EXTS:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 12000:
                    content = content[:12000] + "\n\n… [content truncated for length] …"
                file_context = (
                    f"\n\nThe user has attached a file named **{path.name}**. "
                    f"Here is its content:\n\n```\n{content}\n```"
                )
            except Exception as exc:
                file_context = f"\n\n[Note: Could not read attached file '{path.name}': {exc}]"
        elif path.exists():
            file_context = (
                f"\n\n[Note: The user attached '{path.name}' but it is a binary file. "
                f"Use the RAG or Multimodal agent for this file type.]"
            )

    # Build conversation history context
    history_context = ""
    if history:
        history_context = (
            "\n\nHere is the recent conversation history for context:\n"
            f"{history}\n\n"
            "Use this history to maintain continuity. If the user refers to "
            "something discussed earlier, use the history to respond accurately."
        )

    messages = [
        SystemMessage(
            content=(
                "You are the General Assistant inside Ensō (Multi Agent AI Hub). "
                "You are helpful, accurate, and concise. Answer the user's question to the best "
                "of your ability. If you are unsure, say so. Format responses in Markdown when it "
                "aids readability."
                + history_context
            )
        ),
        HumanMessage(content=query + file_context),
    ]

    response = await llm.ainvoke(messages)
    add_tokens(response)
    return response.content
