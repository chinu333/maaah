"""RAG Agent — retrieval-augmented generation over an Azure AI Search index.

Workflow:
1.  Connect to the Azure AI Search index specified in `AZURE_SEARCH_INDEX_NAME`.
2.  Embed the user query with Azure OpenAI embeddings.
3.  Perform a vector similarity search to retrieve the top-k chunks.
4.  Pass the retrieved context + query to Azure OpenAI for a grounded answer.

The index is assumed to already exist and be populated (e.g. via Azure
AI Search indexer, push API, or a separate ingestion pipeline).

Authentication uses **DefaultAzureCredential** (role-based access) for both
Azure OpenAI and Azure AI Search — no API keys required.
"""

from __future__ import annotations

import logging
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain.chains import RetrievalQA

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Azure credential singleton
# ---------------------------------------------------------------------------

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Search the existing Azure AI Search index and return a grounded answer."""
    settings = get_settings()

    # Strip a leading "RAG" / "rag" prefix the user may have typed so the
    # actual search query is clean.
    clean_query = query
    stripped = query.strip()
    for prefix in ("RAG ", "rag ", "Rag ", "RAG:", "rag:", "Rag:"):
        if stripped.startswith(prefix):
            clean_query = stripped[len(prefix):].strip()
            break

    if not clean_query:
        return "Please provide a question after the RAG prefix so I can search the index."

    logger.info(
        "RAG: searching index '%s' at %s",
        settings.azure_search_index_name,
        settings.azure_search_endpoint,
    )

    # 1. Embeddings model (for query vectorisation)
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
    )

    # 2. Connect to the *existing* Azure AI Search index (read-only)
    vectorstore = AzureSearch(
        azure_search_endpoint=settings.azure_search_endpoint,
        azure_search_key=None,   # RBAC – no key needed
        index_name=settings.azure_search_index_name,
        embedding_function=embeddings.embed_query,
        credential=_credential,
        search_type="hybrid",
    )

    # 3. Build a RetrievalQA chain — retrieves top-k then asks the LLM
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=0.2,
        request_timeout=settings.request_timeout,
    )
    llm.name = "rag-agent-llm"

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(),
        return_source_documents=False,
    )

    result = await qa_chain.ainvoke({"query": clean_query})
    answer = result.get("result", str(result))

    if not answer or answer.strip().lower() in ("i don't know", "i don't know."):
        return (
            f"I searched the **{settings.azure_search_index_name}** index but "
            "couldn't find relevant information. Try rephrasing your question."
        )

    return answer
