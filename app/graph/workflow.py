"""LangGraph agent orchestration workflow with **auto-routing** and **memory**.

The workflow automatically determines which agent(s) to invoke based on:
- Attached file type (image → multimodal, document → rag)
- Query keywords (space/nasa → nasa, document refs → rag)
- Fallback → general agent

Multiple agents can be invoked in parallel and their responses combined.
Conversation history is preserved across turns via LangGraph's MemorySaver.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any, Optional, TypedDict

from langsmith import traceable
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.mcp.server import dispatch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_DOC_EXTS = {".txt", ".md", ".pdf", ".csv", ".json", ".docx", ".xlsx"}

_NASA_KEYWORDS = {
    "nasa", "space", "apod", "mars", "rover", "asteroid", "nebula",
    "galaxy", "planet", "satellite", "spacecraft", "rocket", "astronomy",
    "cosmos", "near earth", "neo", "picture of the day", "hubble",
    "james webb", "jwst", "orbit", "comet", "meteor", "solar system",
    "moon landing", "iss", "international space station",
}

_WEATHER_KEYWORDS = {
    "weather", "temperature", "forecast", "rain", "snow", "sunny",
    "cloudy", "humidity", "wind speed", "uv index", "heat",
    "cold", "storm", "thunder", "hail", "fog", "climate",
    "feels like", "dew point", "barometer", "precipitation",
}

_TRAFFIC_KEYWORDS = {
    "traffic", "route", "directions", "driving", "commute",
    "drive from", "how long to drive", "road", "highway",
    "travel time", "distance from", "eta", "navigation",
    "traffic from", "route from", "directions from",
}

_SQL_KEYWORDS = {
    "sql", "database", "northwind", "query", "table",
    "customers", "orders", "products", "employees", "suppliers",
    "categories", "shippers", "territories", "regions",
    "order details", "how many orders", "top selling",
    "total sales", "revenue", "most ordered", "least ordered",
    "employee list", "customer list", "product list",
    "average price", "total quantity", "inventory",
}

_VIZ_KEYWORDS = {
    "chart", "graph", "plot", "visualize", "visualization",
    "bar chart", "pie chart", "bubble chart", "line chart",
    "histogram", "donut", "area chart", "scatter",
    "show me a chart", "draw a chart", "create a chart",
    "stacked bar", "grouped bar", "horizontal bar",
    "visualise", "diagram", "infographic",
}


@traceable(name="classify_agents", run_type="chain", tags=["routing"])
def classify_agents(query: str, file_path: Optional[str] = None) -> list[str]:
    """Rule-based classifier: pick one or more agents based on query + file."""
    agents: list[str] = []
    q = query.lower().strip()

    # ── Explicit RAG prefix → always route to RAG ───────────────
    if q.startswith("rag ") or q.startswith("rag:"):
        agents.append("rag")
        return agents

    # ── File-based routing ──────────────────────────────────────
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _IMAGE_EXTS:
            agents.append("multimodal")
        elif ext in _DOC_EXTS:
            agents.append("rag")

    # ── NASA keyword routing ────────────────────────────────────
    if any(kw in q for kw in _NASA_KEYWORDS):
        agents.append("nasa")

    # ── Weather keyword routing ─────────────────────────────────
    if any(kw in q for kw in _WEATHER_KEYWORDS):
        agents.append("weather")

    # ── Traffic keyword routing ─────────────────────────────────
    if any(kw in q for kw in _TRAFFIC_KEYWORDS):
        agents.append("traffic")

    # ── SQL / Northwind keyword routing ───────────────────────
    if any(kw in q for kw in _SQL_KEYWORDS):
        agents.append("sql")

    # ── Visualization keyword routing ─────────────────────────
    if any(kw in q for kw in _VIZ_KEYWORDS):
        agents.append("viz")

    # ── Document / search hints (no file currently attached) ────
    if not file_path:
        rag_hints = [
            "document", "uploaded", "search the file", "find in file",
            "my file", "the file", "the pdf", "the csv", "retrieve",
            "search index", "internal search", "knowledge base",
        ]
        if any(h in q for h in rag_hints):
            agents.append("rag")

    # ── Fallback to general ─────────────────────────────────────
    if not agents:
        agents.append("general")

    # Deduplicate while preserving order
    return list(dict.fromkeys(agents))


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
    history = state.get("messages") or []
    agents = classify_agents(query, file_path)
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
            result = await dispatch(agent_name, query, file_path, history=history_block)
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
    new_messages = [
        {"role": "user", "content": query},
        {"role": "assistant", "content": resp},
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
    initial_state: AgentState = {
        "query": query,
        "file_path": file_path,
        "agents_called": [],
        "response": "",
        "error": None,
        "messages": [],
    }

    result = await workflow.ainvoke(
        initial_state,
        config={
            "run_name": "MAAAH-Orchestrator",
            "configurable": {"thread_id": session_id},
        },
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    return {
        "response": result["response"],
        "agents_called": result["agents_called"],
    }
