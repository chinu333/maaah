"""MCP (Model Context Protocol) compatible server.

Exposes each Ensō agent as an MCP tool so that external orchestrators
or the built-in LangGraph workflow can invoke them uniformly.

The server is implemented as a thin wrapper that conforms to the MCP
tool-call interface while delegating to individual agent modules.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langsmith import traceable

from app.agents import rag_agent, multimodal_agent, nasa_agent, general_agent, weather_agent, traffic_agent, sql_agent, viz_agent, cicp_agent, ida_agent, fhir_agent, banking_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "rag_search",
        "description": (
            "Search through locally uploaded documents using RAG "
            "(Retrieval-Augmented Generation) backed by Azure AI Search "
            "and Azure OpenAI. Best for questions about uploaded files "
            "such as PDFs, CSVs, or text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's question."},
                "file_path": {
                    "type": "string",
                    "description": "Optional path to a specific uploaded file.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "multimodal_analysis",
        "description": (
            "Analyse images together with text using Azure OpenAI "
            "vision-capable deployment. Supports PNG, JPG, GIF, and WebP."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's question or instruction."},
                "file_path": {
                    "type": "string",
                    "description": "Path to the image file to analyse.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "nasa_query",
        "description": (
            "Query NASA public APIs for space-related data including APOD, "
            "Mars rover photos, Near-Earth Objects, and NASA image search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's space-related question."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "general_assistant",
        "description": (
            "A general-purpose AI assistant for any question that does not "
            "involve uploaded documents, images, or NASA data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's question."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "weather_lookup",
        "description": (
            "Get current weather conditions for a location using Azure Maps. "
            "Provides temperature, humidity, wind, UV index, and more."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's weather-related question including a location."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "traffic_route",
        "description": (
            "Get traffic and route information between two locations using "
            "TomTom. Provides travel time, distance, delays, and ETA."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's traffic/route question with origin and destination."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sql_query",
        "description": (
            "Query the Northwind SQLite database using natural language. "
            "Generates SQL, executes it, and returns a natural-language answer "
            "with data tables. Covers customers, orders, products, employees, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's question about the Northwind database."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "visualize_data",
        "description": (
            "Create data visualizations (bar chart, pie chart, bubble chart, "
            "line chart, histogram, etc.) from the Northwind SQLite database. "
            "Generates SQL, fetches data, and returns an embedded chart image."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's visualization request."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "cicp_process",
        "description": (
            "Car Insurance Claim Processing (CICP) agent. Analyses an uploaded "
            "claim form and damaged car photo, retrieves applicable insurance "
            "rules from the cicp vector index, and renders an APPROVE / REJECT "
            "decision. Requires both a claim form (document) and damage photo "
            "(image) to be uploaded."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's insurance claim request."},
                "file_path": {
                    "type": "string",
                    "description": "Path to uploaded file (claim form or damage photo).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ida_design",
        "description": (
            "Interior Design Agent (IDA). Analyses a room image, suggests "
            "complementary furniture, and searches the RTG product catalogue "
            "for matching items with product IDs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's interior design question."},
                "file_path": {
                    "type": "string",
                    "description": "Path to the room image to analyse.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fhir_convert",
        "description": (
            "FHIR Data Conversion Agent. Converts healthcare data (CSV, HL7v2, "
            "CDA, free-text clinical notes) into valid FHIR R4 JSON resources. "
            "Generates Patient, Observation, Condition, MedicationRequest, and "
            "other FHIR resources with proper coding (SNOMED CT, LOINC, ICD-10)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's FHIR conversion or healthcare data question."},
                "file_path": {
                    "type": "string",
                    "description": "Path to the source healthcare data file (CSV, JSON, XML, HL7, etc.).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "banking_assist",
        "description": (
            "Banking Customer Service Agent. Answers questions about customer "
            "accounts, transactions, loans, cards, fraud alerts, support tickets, "
            "and branch information from the banking database. Also retrieves "
            "bank policies, fee schedules, interest rates, overdraft rules, and "
            "regulatory information from the bank policy handbook."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's banking question."},
            },
            "required": ["query"],
        },
    },
]

# Map tool names to agent invoke functions
_TOOL_HANDLERS = {
    "rag_search": rag_agent.invoke,
    "multimodal_analysis": multimodal_agent.invoke,
    "nasa_query": nasa_agent.invoke,
    "general_assistant": general_agent.invoke,
    "weather_lookup": weather_agent.invoke,
    "traffic_route": traffic_agent.invoke,
    "sql_query": sql_agent.invoke,
    "visualize_data": viz_agent.invoke,
    "cicp_process": cicp_agent.invoke,
    "ida_design": ida_agent.invoke,
    "fhir_convert": fhir_agent.invoke,
    "banking_assist": banking_agent.invoke,
}


# ---------------------------------------------------------------------------
# MCP-compatible server class
# ---------------------------------------------------------------------------


class MCPServer:
    """Minimal MCP-compatible tool server."""

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions (MCP ``tools/list`` equivalent)."""
        return TOOL_DEFINITIONS

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a tool by name (MCP ``tools/call`` equivalent)."""
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = await handler(**arguments)
            return {"result": result}
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return {"error": str(exc)}


# Singleton
mcp_server = MCPServer()


# ---------------------------------------------------------------------------
# Mapping helpers used by routes
# ---------------------------------------------------------------------------

AGENT_TO_TOOL: dict[str, str] = {
    "rag": "rag_search",
    "multimodal": "multimodal_analysis",
    "nasa": "nasa_query",
    "general": "general_assistant",
    "weather": "weather_lookup",
    "traffic": "traffic_route",
    "sql": "sql_query",
    "viz": "visualize_data",
    "cicp": "cicp_process",
    "ida": "ida_design",
    "fhir": "fhir_convert",
    "banking": "banking_assist",
}


async def dispatch(
    agent_name: str,
    query: str,
    file_path: Optional[str] = None,
    history: str = "",
    session_id: str = "default",
) -> str:
    """Convenience dispatcher: agent name → MCP tool call → result string."""
    tool_name = AGENT_TO_TOOL.get(agent_name, "general_assistant")
    args: dict[str, Any] = {"query": query}
    if file_path:
        args["file_path"] = file_path
    if history:
        args["history"] = history
    if session_id:
        args["session_id"] = session_id

    @traceable(name=f"{agent_name}_agent", run_type="tool", tags=["agent", agent_name])
    async def _traced_call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await mcp_server.call_tool(tool, arguments)

    response = await _traced_call(tool_name, args)
    if "error" in response:
        raise RuntimeError(response["error"])
    return response["result"]
