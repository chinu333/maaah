"""LangGraph agent orchestration workflow with **auto-routing** and **memory**.

The workflow automatically determines which agent(s) to invoke using an
**LLM-based classifier** that understands complex, multi-intent queries.
File-based routing (image → multimodal, document → rag) is applied as a
deterministic pre-filter before the LLM classifier runs.

Multiple agents can be invoked in parallel and their responses combined.
Conversation history is preserved across turns via LangGraph's MemorySaver.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.mcp.server import dispatch
from app.utils.token_counter import add_tokens, reset_counter, get_totals
from app.utils.llm_cache import get_chat_llm
from app.agents.evaluator_agent import evaluate_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_DOC_EXTS = {".txt", ".md", ".pdf", ".csv", ".json", ".docx", ".xlsx"}

_VALID_AGENTS = {"general", "rag", "multimodal", "nasa", "weather", "traffic", "sql", "viz", "cicp", "ida", "fhir", "banking"}

# ---------------------------------------------------------------------------
# LLM-based classifier prompt
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM_PROMPT = """\
You are an intelligent request router for a multi-agent system.
Your ONLY job is to decide which agent(s) should handle a user's query.

Available agents and their capabilities:
- **general**: General-purpose chat assistant. Handles greetings, open-ended questions, opinions, explanations, math, coding help, or anything that doesn't clearly belong to another agent.
- **rag**: Searches an indexed knowledge base / document store for company policies, compliance documents, internal guidelines, uploaded documents, or any domain-specific content.
- **multimodal**: Analyzes images combined with text (only relevant when an image file is attached).
- **nasa**: NASA space data — Astronomy Picture of the Day (APOD), Mars rover photos, near-Earth objects (NEO), asteroid data, space imagery.
- **weather**: Current weather conditions, temperature, forecast for any location.
- **traffic**: Driving routes, traffic conditions, travel time, distance, and directions between locations.
- **sql**: Queries the Northwind sample database — customers, orders, products, employees, suppliers, categories, sales data, revenue, inventory, rankings.
- **viz**: Creates charts, graphs, and visualizations (bar, pie, line, scatter, histogram, etc.) — typically from database data. If data needs to be queried first, also include "sql".
- **cicp**: Car Insurance Claim Processing — handles insurance claim submissions. Analyses uploaded claim forms, assesses damaged car photos, applies insurance policy rules, and renders APPROVE/REJECT decisions. Route here when the user mentions insurance claims, car damage claims, claim processing, or uploading claim forms / damage photos.
- **ida**: Interior Design Agent — analyses a room image, suggests furniture that complements the space (style, colour, layout), and searches the RTG product catalogue for matching items. Route here when the user mentions interior design, room design, furniture suggestions, room makeover, decorating a room, or home styling. Requires an attached room image.
- **fhir**: FHIR Data Conversion Agent — converts healthcare data into FHIR R4 JSON resources. Handles CSV-to-FHIR, HL7v2-to-FHIR, CDA-to-FHIR, free-text clinical notes to FHIR, resource generation from descriptions, Bundle assembly, and terminology mapping (SNOMED CT, LOINC, ICD-10, RxNorm). Route here when the user mentions FHIR, HL7, healthcare data conversion, clinical data mapping, patient resources, observations, conditions, medication requests, FHIR bundles, interoperability, EHR data, or medical coding systems.
- **banking**: Banking Customer Service Agent — answers questions about bank customers, accounts, balances, transactions, loans, cards, fraud alerts, support tickets, branches, and bank policies (fee schedules, interest rates, overdraft rules, wire transfer rules, card policies, regulatory compliance). Route here when the user mentions bank account, balance, transaction history, loan status, credit card, debit card, fraud alert, support ticket, branch, bank fee, overdraft, wire transfer, interest rate, bank policy, or any retail/consumer banking topic.

Rules:
1. Return ONLY a JSON array of agent name strings, e.g. ["sql", "viz", "weather"].
2. Select ALL agents needed to fully answer the query. Complex queries often need multiple agents.
3. If a visualization is requested from database data, include BOTH "sql" and "viz".
4. If the query mentions policies, compliance, guidelines, or internal documents, include "rag".
5. If no specialized agent fits, use ["general"].
6. Do NOT include "multimodal" unless an image file is explicitly attached AND the query is NOT about insurance claims.
7. For insurance claim processing, use "cicp" — do NOT use "multimodal" or "rag" separately for claim-related queries.
8. For interior design / room design / furniture suggestions with a room image, use "ida" — do NOT use "multimodal" separately.
9. For FHIR or healthcare data conversion queries, use "fhir" — do NOT use "general" or "rag" for FHIR-specific questions.
10. For banking questions (accounts, transactions, loans, cards, fraud, fees, interest rates, bank policies, overdraft, wire transfers, support tickets, branches), use "banking" — do NOT use "sql" or "rag" for banking-specific questions.
11. **Follow-up questions**: If conversation context is provided, check which agent handled the previous turn. If the current query is a follow-up (e.g. "what is the property id?", "show me more details", "what about X?"), route to the SAME agent that answered the prior turn — do NOT default to "general".
12. Return valid JSON only — no explanations, no markdown, no extra text.
"""


@traceable(name="classify_agents", run_type="chain", tags=["routing"])
async def classify_agents(
    query: str,
    file_path: Optional[str] = None,
    history: list[dict[str, str]] | None = None,
) -> list[str]:
    """LLM-based classifier: analyse the query and pick one or more agents.

    File-based routing is applied deterministically first. Then the LLM
    decides which additional agents are needed for the textual query.
    Conversation history is passed so follow-up questions can be routed
    to the same agent that handled the previous turn.
    """
    agents: list[str] = []
    q = query.lower().strip()

    # ── Explicit RAG prefix → always route to RAG ───────────────
    if q.startswith("rag ") or q.startswith("rag:"):
        return ["rag"]

    # ── File-based routing (deterministic pre-filter) ───────────
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _IMAGE_EXTS:
            agents.append("multimodal")
        elif ext in _DOC_EXTS:
            agents.append("rag")

    # ── LLM-based classification ────────────────────────────────
    try:
        llm_agents = await _llm_classify(query, file_path, history)
        agents.extend(llm_agents)
    except Exception as exc:
        logger.warning("LLM classifier failed (%s), falling back to keyword matcher", exc)
        agents.extend(_keyword_fallback(q))

    # Deduplicate while preserving order
    agents = list(dict.fromkeys(agents))

    # Validate — keep only known agent names
    agents = [a for a in agents if a in _VALID_AGENTS]

    # If CICP is selected, it handles doc + image analysis internally,
    # so remove redundant multimodal/rag that the file pre-filter may have added.
    if "cicp" in agents:
        agents = [a for a in agents if a not in ("multimodal", "rag")]

    # IDA handles its own image analysis — remove redundant multimodal.
    if "ida" in agents:
        agents = [a for a in agents if a != "multimodal"]

    # Fallback to general if nothing matched
    if not agents:
        agents.append("general")

    return agents


async def _llm_classify(
    query: str,
    file_path: Optional[str] = None,
    history: list[dict[str, str]] | None = None,
) -> list[str]:
    """Call Azure OpenAI to classify which agents should handle the query.

    Recent conversation history is included so the classifier can understand
    follow-up questions and route them to the agent that handled the prior turn.
    Uses a cached LLM singleton for HTTP connection reuse.
    """
    llm = get_chat_llm(temperature=0.0, max_tokens=50, name="enso-classifier")

    # Build conversation context for the classifier (last 6 messages = 3 turns)
    history_block = ""
    if history:
        recent = history[-6:]
        lines = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            if len(content) > 300:
                content = content[:300] + "…"
            lines.append(f"{role}: {content}")
        history_block = "\n".join(lines)

    user_content = ""
    if history_block:
        user_content += f"Recent conversation context:\n{history_block}\n\n"
    user_content += f"User query: {query}"
    if file_path:
        user_content += f"\nAttached file: {Path(file_path).name}"

    response = await llm.ainvoke([
        SystemMessage(content=_CLASSIFIER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ])
    add_tokens(response)

    raw = response.content.strip()
    # Strip markdown code fences if model wraps them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)
    if isinstance(parsed, list):
        return [str(a).lower().strip() for a in parsed]
    raise ValueError(f"Expected JSON array, got: {type(parsed)}")


def _keyword_fallback(q: str) -> list[str]:
    """Lightweight keyword matcher used as fallback if LLM classifier fails."""
    agents: list[str] = []

    _NASA_KW = {"nasa", "space", "apod", "mars", "rover", "asteroid", "nebula",
                "galaxy", "planet", "satellite", "spacecraft", "rocket", "astronomy",
                "cosmos", "hubble", "james webb", "jwst", "orbit", "comet", "meteor"}
    _WEATHER_KW = {"weather", "temperature", "forecast", "rain", "snow", "sunny",
                   "cloudy", "humidity", "wind speed", "storm", "climate"}
    _TRAFFIC_KW = {"traffic", "route", "directions", "driving", "commute",
                   "drive from", "travel time", "distance from", "eta", "navigation"}
    _SQL_KW = {"sql", "database", "northwind", "customers", "orders", "products",
               "employees", "suppliers", "total sales", "revenue", "inventory"}
    _VIZ_KW = {"chart", "graph", "plot", "visualize", "visualization", "pie chart",
               "bar chart", "line chart", "histogram", "scatter"}
    _RAG_KW = {"document", "policy", "compliance", "guideline", "knowledge base",
               "internal search", "the pdf", "the csv", "retrieve", "uploaded"}
    _CICP_KW = {"insurance claim", "car claim", "claim form", "damage claim",
                "claim processing", "car insurance", "vehicle claim", "auto claim",
                "cicp", "claim decision", "approve claim", "reject claim"}
    _IDA_KW = {"interior design", "room design", "furniture suggest", "room makeover",
               "decorating", "home styling", "room image", "design this room",
               "ida", "furnish", "room layout", "rtg"}

    if any(kw in q for kw in _NASA_KW):   agents.append("nasa")
    if any(kw in q for kw in _WEATHER_KW): agents.append("weather")
    if any(kw in q for kw in _TRAFFIC_KW): agents.append("traffic")
    if any(kw in q for kw in _SQL_KW):     agents.append("sql")
    if any(kw in q for kw in _VIZ_KW):     agents.append("viz")
    if any(kw in q for kw in _RAG_KW):     agents.append("rag")
    if any(kw in q for kw in _CICP_KW):    agents.append("cicp")
    _BANKING_KW = {"bank account", "bank balance", "bank transaction", "bank fee",
                   "overdraft", "wire transfer", "bank policy", "loan status",
                   "credit card balance", "debit card", "fraud alert", "support ticket",
                   "banking", "bank branch", "interest rate on", "monthly payment",
                   "bank customer", "account balance", "card reward"}
    if any(kw in q for kw in _IDA_KW):     agents.append("ida")
    if any(kw in q for kw in _BANKING_KW): agents.append("banking")

    if not agents:
        agents.append("general")
    return agents


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


def _append_messages(
    existing: list[dict[str, str]], new: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Reducer that appends new messages to the conversation history."""
    return (existing or []) + (new or [])


class AgentState(TypedDict):
    """State passed through the LangGraph workflow."""
    query: str
    file_path: Optional[str]
    session_id: str
    agents_called: list[str]
    response: str
    error: Optional[str]
    messages: Annotated[list[dict[str, str]], _append_messages]


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def orchestrate_node(state: AgentState) -> dict[str, Any]:
    """Classify the query, call the appropriate agent(s), combine results."""
    query = state["query"]
    file_path = state.get("file_path")
    session_id = state.get("session_id", "default")
    history = state.get("messages") or []

    # ── Detect active CICP session from conversation history ────
    # CICP is multi-turn: it prompts for files across several turns.
    # If a recent assistant message contains CICP markers, force-route
    # to cicp so intermediate uploads don't get misclassified.
    _cicp_active = False
    for msg in reversed(history[-10:]):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if "CICP" in content or "Car Insurance Claim Processing" in content:
                _cicp_active = True
            break  # only check the most recent assistant message

    if _cicp_active:
        agents = ["cicp"]
        logger.info("Auto-routed to cicp (active CICP session detected)")
    else:
        agents = await classify_agents(query, file_path, history)
        logger.info("Auto-routed to agent(s): %s", agents)

    # Build a compact history summary for agents that benefit from context.
    # Keep the last 10 turns (user+assistant pairs) to stay within token limits.
    recent = history[-20:]  # each turn = 2 messages
    history_block = ""
    if recent:
        lines = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            # Truncate very long assistant responses for the context window
            if len(content) > 400:
                content = content[:400] + "…"
            lines.append(f"{role}: {content}")
        history_block = "\n".join(lines)

    @traceable(run_type="chain", tags=["agent-call"])
    async def _call_agent(agent_name: str, query: str, file_path: Optional[str]) -> tuple[str, str]:
        try:
            result = await dispatch(agent_name, query, file_path, history=history_block, session_id=session_id)
            return agent_name, result
        except Exception as exc:
            logger.exception("Agent %s failed", agent_name)
            return agent_name, f"\u26a0 {agent_name} agent error: {exc}"

    results = await asyncio.gather(
        *[_call_agent(a, query, file_path) for a in agents]
    )

    called = [name for name, _ in results]

    if len(results) == 1:
        _, resp = results[0]
    else:
        # Combine multi-agent responses
        sections = []
        for name, resp in results:
            sections.append(f"### 🤖 {name.upper()} Agent\n\n{resp}")
        resp = "\n\n---\n\n".join(sections)

    # Append this turn to conversation history
    # Include agents_called so follow-up routing can detect the previous agent.
    new_messages = [
        {"role": "user", "content": query},
        {"role": "assistant", "content": resp, "agents": called},
    ]

    return {
        "response": resp,
        "agents_called": called,
        "error": None,
        "messages": new_messages,
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------


def build_workflow():
    """Construct and compile the LangGraph workflow with memory."""
    memory = MemorySaver()
    graph = StateGraph(AgentState)
    graph.add_node("orchestrate", orchestrate_node)
    graph.set_entry_point("orchestrate")
    graph.add_edge("orchestrate", END)
    return graph.compile(checkpointer=memory)


# Pre-compiled workflow singleton
workflow = build_workflow()


async def run_workflow(
    query: str,
    file_path: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """Execute the compiled workflow and return response + agents_called."""
    # Reset per-request token counter
    reset_counter()

    initial_state: AgentState = {
        "query": query,
        "file_path": file_path,
        "session_id": session_id,
        "agents_called": [],
        "response": "",
        "error": None,
        "messages": [],
    }

    result = await workflow.ainvoke(
        initial_state,
        config={
            "run_name": "Enso-Orchestrator",
            "configurable": {"thread_id": session_id},
        },
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    # ── Inline auto-evaluation ──────────────────────────────────
    evaluation_scores = {}
    try:
        evaluation_scores = await evaluate_response(
            query=query,
            response=result["response"],
        )
    except Exception as exc:
        logger.warning("Inline evaluation failed (non-blocking): %s", exc)

    return {
        "response": result["response"],
        "agents_called": result["agents_called"],
        "token_usage": get_totals(),
        "evaluation_scores": evaluation_scores,
    }
