"""Shared LLM, Embeddings & VectorStore singletons.

Avoids recreating Azure OpenAI / AI Search clients on every request,
enabling HTTP connection reuse (TCP + TLS) and faster response times.

All objects are created lazily on first use and cached for the lifetime
of the process.  Thread-safety is provided by Python's GIL and by the
fact that ``AzureChatOpenAI.ainvoke`` is concurrency-safe.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores.azuresearch import AzureSearch

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared Azure credential + token provider (created once at import time)
# ---------------------------------------------------------------------------

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)


def get_credential() -> DefaultAzureCredential:
    """Return the shared ``DefaultAzureCredential``."""
    return _credential


def get_token_provider():
    """Return the shared bearer-token provider for Azure OpenAI."""
    return _token_provider


# ---------------------------------------------------------------------------
# Cached AzureChatOpenAI instances
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def get_chat_llm(
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    name: str = "cached-llm",
    request_timeout: int | None = None,
) -> AzureChatOpenAI:
    """Return a **cached** ``AzureChatOpenAI`` keyed by its configuration.

    The underlying ``httpx.AsyncClient`` is reused across calls, saving
    TCP + TLS setup time (~200-400 ms per request).
    """
    settings = get_settings()
    kwargs: dict = dict(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=temperature,
        request_timeout=request_timeout or settings.request_timeout,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    llm = AzureChatOpenAI(**kwargs)
    llm.name = name
    logger.debug("Created & cached LLM: %s (temp=%s, max_tokens=%s)", name, temperature, max_tokens)
    return llm


# ---------------------------------------------------------------------------
# Cached AzureOpenAIEmbeddings
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def get_embeddings() -> AzureOpenAIEmbeddings:
    """Return a **cached** ``AzureOpenAIEmbeddings`` instance."""
    settings = get_settings()
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
    )


# ---------------------------------------------------------------------------
# Cached AzureSearch vector stores (keyed by index name)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def get_vectorstore(index_name: str) -> AzureSearch:
    """Return a **cached** ``AzureSearch`` vector store for *index_name*."""
    settings = get_settings()
    embeddings = get_embeddings()
    return AzureSearch(
        azure_search_endpoint=settings.azure_search_endpoint,
        azure_search_key=None,
        index_name=index_name,
        embedding_function=embeddings.embed_query,
        credential=_credential,
        search_type="hybrid",
    )
