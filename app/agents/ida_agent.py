"""Interior Design Agent (IDA) — room analysis, furniture suggestions & product search.

Sub-agents / tasks:
1. **Room Analyser** — uses Azure OpenAI vision to analyse a room image (layout,
   style, colours, lighting, dimensions estimate).
2. **Furniture Advisor** — takes the room analysis and suggests furniture pieces
   that complement the space (style-matched, size-appropriate).
3. **Product Searcher** — searches the hard-coded ``rtg`` Azure AI Search vector
   index for products matching each furniture suggestion and returns product IDs.

The ``rtg`` index name is intentionally hard-coded and does NOT use the
``AZURE_SEARCH_INDEX_NAME`` from settings (that one is reserved for the RAG agent).

Authentication uses **DefaultAzureCredential** (role-based access).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.agents import multimodal_agent

logger = logging.getLogger(__name__)

# Hard-coded index for RTG product catalogue
_RTG_INDEX_NAME = "rtg-products"

# Azure credential singleton
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_llm(temperature: float = 0.3) -> AzureChatOpenAI:
    """Return a reusable Azure OpenAI Chat LLM instance."""
    settings = get_settings()
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=temperature,
        request_timeout=settings.request_timeout,
    )
    llm.name = "ida-agent-llm"
    return llm


# ---------------------------------------------------------------------------
# Sub-agent 1 — Room Analyser (delegates to multimodal agent)
# ---------------------------------------------------------------------------


async def _analyse_room(image_path: str, query: str) -> str:
    """Delegate room image analysis to the multimodal agent."""
    prompt = (
        f"{query}\n\n"
        "You are an expert interior designer analysing a room photograph.\n"
        "Provide a detailed analysis covering:\n"
        "1. **Room Type** — living room, bedroom, kitchen, office, dining room, etc.\n"
        "2. **Dimensions Estimate** — approximate size (small / medium / large / open-plan).\n"
        "3. **Current Style** — modern, traditional, minimalist, industrial, bohemian, etc.\n"
        "4. **Colour Palette** — dominant wall, floor, and accent colours.\n"
        "5. **Lighting** — natural light level, existing fixtures.\n"
        "6. **Existing Furniture** — list what's already in the room.\n"
        "7. **Gaps & Opportunities** — areas that feel empty or could benefit from new furniture.\n\n"
        "Be specific and concise. This analysis will be used to recommend furniture."
    )
    return await multimodal_agent.invoke(prompt, file_path=image_path)


# ---------------------------------------------------------------------------
# Sub-agent 2 — Furniture Advisor
# ---------------------------------------------------------------------------

_FURNITURE_ADVISOR_PROMPT = """\
You are an expert interior design furniture advisor.
Based on the room analysis provided, suggest **5 to 8 specific furniture pieces**
that would complement the space.

For EACH suggestion provide:
- **Item** — e.g. "3-seater fabric sofa", "round walnut coffee table"
- **Why** — how it complements the room's style, colour palette, and dimensions
- **Search Keywords** — 3-5 keywords suitable for searching a furniture product catalogue

Format your response as a numbered list. Be practical and style-appropriate.
After the list, output a section titled "## Search Queries" with one search query
per line (just the keywords, no numbering) that can be used to find these products
in a retail catalogue.
"""


async def _suggest_furniture(room_analysis: str, query: str) -> str:
    """LLM suggests furniture based on room analysis."""
    llm = _get_llm(temperature=0.4)
    response = await llm.ainvoke([
        SystemMessage(content=_FURNITURE_ADVISOR_PROMPT),
        HumanMessage(content=(
            f"User request: {query}\n\n"
            f"## Room Analysis\n{room_analysis}"
        )),
    ])
    add_tokens(response)
    return response.content


# ---------------------------------------------------------------------------
# Sub-agent 3 — Product Searcher (RTG vector index)
# ---------------------------------------------------------------------------

async def _search_products(suggestions_text: str) -> str:
    """Search the RTG vector index for products matching furniture suggestions.

    Parses the "## Search Queries" section from the advisor output and runs
    one hybrid search per query line, collecting product IDs and titles.
    """
    settings = get_settings()

    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
    )

    vectorstore = AzureSearch(
        azure_search_endpoint=settings.azure_search_endpoint,
        azure_search_key=None,  # RBAC
        index_name=_RTG_INDEX_NAME,
        embedding_function=embeddings.embed_query,
        credential=_credential,
        search_type="hybrid",
    )

    # Extract search queries from the "## Search Queries" section
    queries: list[str] = []
    in_section = False
    for line in suggestions_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## search quer"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("##"):
                break  # Next section
            if stripped:
                queries.append(stripped)

    if not queries:
        # Fallback: use the full suggestions text as a single query
        queries = [suggestions_text[:500]]

    results_parts: list[str] = []
    seen_ids: set[str] = set()

    for search_query in queries:
        try:
            docs = vectorstore.similarity_search(search_query, k=3)
        except Exception as exc:
            logger.warning("RTG search failed for '%s': %s", search_query, exc)
            continue

        for doc in docs:
            meta = doc.metadata or {}
            product_id = (
                meta.get("product_id")
                or meta.get("id")
                or meta.get("sku")
                or meta.get("chunk_id")
                or "N/A"
            )
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            title = (
                meta.get("title")
                or meta.get("product_name")
                or meta.get("name")
                or doc.page_content[:80]
            )
            price = meta.get("price", "")
            price_str = f" — ${price}" if price else ""
            category = meta.get("category", "")
            cat_str = f" | Category: {category}" if category else ""

            results_parts.append(
                f"- **Product ID:** {product_id} | **{title}**{price_str}{cat_str}"
            )

    if not results_parts:
        return (
            "No matching products were found in the RTG catalogue. "
            "The index may not contain items matching these suggestions."
        )

    return "## Matching Products from RTG Catalogue\n\n" + "\n".join(results_parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Orchestrate the three IDA sub-agents to produce a complete response."""

    has_image = False
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _IMAGE_EXTS:
            has_image = True

    if not has_image:
        return (
            "**Interior Design Agent** requires a room image to analyse. "
            "Please upload a photo of the room you'd like design suggestions for, "
            "then ask your question again."
        )

    # ── Step 1: Analyse the room ────────────────────────────────
    logger.info("IDA: Step 1 — Analysing room image")
    room_analysis = await _analyse_room(file_path, query)

    # ── Step 2: Suggest furniture ───────────────────────────────
    logger.info("IDA: Step 2 — Suggesting furniture")
    suggestions = await _suggest_furniture(room_analysis, query)

    # ── Step 3: Search RTG product index ────────────────────────
    logger.info("IDA: Step 3 — Searching RTG product index")
    try:
        product_results = await _search_products(suggestions)
    except Exception as exc:
        logger.error("IDA: RTG product search failed: %s", exc)
        product_results = (
            f"⚠️ Product search encountered an error: {exc}\n\n"
            "The furniture suggestions above are still valid — "
            "please search the RTG catalogue manually for matching items."
        )

    # ── Compose final response ──────────────────────────────────
    return (
        "# 🏠 Interior Design Analysis\n\n"
        "## Room Analysis\n\n"
        f"{room_analysis}\n\n"
        "---\n\n"
        "## Furniture Recommendations\n\n"
        f"{suggestions}\n\n"
        "---\n\n"
        f"{product_results}"
    )
