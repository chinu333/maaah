"""Multimodal Agent — handles image + text inputs.

Sends images (base64-encoded) alongside text to a vision-capable Azure OpenAI
deployment (GPT-4o by default) and returns the model's response.

Authentication uses **DefaultAzureCredential** (role-based access).
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)


def _encode_image(image_path: str) -> tuple[str, str]:
    """Read and base64-encode a local image; return (b64_string, mime_type)."""
    path = Path(image_path)
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    with open(path, "rb") as fh:
        b64 = base64.standard_b64encode(fh.read()).decode("utf-8")
    return b64, mime_type


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Analyse an image (if provided) together with the user's text query."""
    settings = get_settings()

    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=0.3,
        request_timeout=settings.request_timeout,
    )
    llm.name = "multimodal-agent-llm"

    content_parts: list[dict] = [{"type": "text", "text": query}]

    if file_path:
        path = Path(file_path)
        if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            b64, mime = _encode_image(str(path))
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
            logger.info("Multimodal: attached image %s (%s)", path.name, mime)
        else:
            content_parts.append(
                {"type": "text", "text": f"\n[Note: Uploaded file '{path.name}' is not a supported image format.]"}
            )

    message = HumanMessage(content=content_parts)
    response = await llm.ainvoke([message])
    return response.content
