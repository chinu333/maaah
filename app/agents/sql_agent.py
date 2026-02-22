"""SQL Agent — natural-language queries against the Northwind SQLite database.

Uses LangChain's ``create_sql_agent`` with ``SQLDatabaseToolkit`` for
autonomous SQL generation, execution, and natural-language answers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.callbacks import BaseCallbackHandler

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)

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

    llm = get_chat_llm(temperature=0.0, name="sql-agent-llm")

    toolkit = SQLDatabaseToolkit(db=_db, llm=llm)

    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="openai-tools",
        handle_parsing_errors=True,
        prefix=(
            "You are the SQL Agent inside Ensō (Multi Agent AI Hub). "
            "You have access to a Northwind SQLite database. Answer the user's "
            "question by querying the database. Always provide:\n"
            "1. A brief natural-language summary\n"
            "2. The data in a Markdown table (if applicable)\n"
            "3. The SQL query you used (in a ```sql code block)\n"
            "Be concise, accurate, and format your response in Markdown."
        ),
    )

    # Callback to capture token usage from the agent's internal LLM calls
    class _TokenCapture(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, "message"):
                        add_tokens(gen.message)

    result = await agent_executor.ainvoke({"input": query}, config={"callbacks": [_TokenCapture()]})
    return result.get("output", str(result))
