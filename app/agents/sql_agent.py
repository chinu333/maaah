"""SQL Agent — natural-language queries against the Northwind SQLite database.

Uses LangChain's ``create_sql_agent`` with ``SQLDatabaseToolkit`` for
autonomous SQL generation, execution, and natural-language answers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "northwind.db"
_DB_URI = f"sqlite:///{_DB_PATH}"

# Create the SQLDatabase instance once
_db = SQLDatabase.from_uri(_DB_URI)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Use the LangChain SQL agent to answer questions about Northwind."""
    settings = get_settings()

    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=0,
        request_timeout=settings.request_timeout,
    )
    llm.name = "sql-agent-llm"

    toolkit = SQLDatabaseToolkit(db=_db, llm=llm)

    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="openai-tools",
        handle_parsing_errors=True,
        prefix=(
            "You are the SQL Agent inside MAAAH (Multi Agent App – Atlanta Hub). "
            "You have access to a Northwind SQLite database. Answer the user's "
            "question by querying the database. Always provide:\n"
            "1. A brief natural-language summary\n"
            "2. The data in a Markdown table (if applicable)\n"
            "3. The SQL query you used (in a ```sql code block)\n"
            "Be concise, accurate, and format your response in Markdown."
        ),
    )

    result = await agent_executor.ainvoke({"input": query})
    return result.get("output", str(result))
