"""Banking Agent — customer-service assistant backed by SQLite + Azure AI Search.

Combines two data sources to answer banking questions:
1. **SQLite** (``db/banking.db``) — customer records, accounts, transactions,
   loans, cards, fraud alerts, support tickets, and branch information.
2. **Azure AI Search** (index ``bank``) — vectorised bank policy document for
   fee schedules, interest rates, overdraft rules, compliance, etc.

The agent first decides whether the question needs *data* (SQL), *policy* (RAG),
or *both*, then executes the appropriate pipeline(s) and combines the results
into a single, well-formatted Markdown answer.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_openai import AzureChatOpenAI
from langchain.chains import RetrievalQA
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm, get_vectorstore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BANK_INDEX_NAME = "bank"  # hardcoded Azure AI Search index

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "banking.db"
_DB_URI = f"sqlite:///{_DB_PATH}"

# SQLite database (created once)
_db = SQLDatabase.from_uri(_DB_URI)

# ---------------------------------------------------------------------------
# System prompt for the SQL sub-agent
# ---------------------------------------------------------------------------

_SQL_PREFIX = """\
You are the Banking SQL Agent inside Enso (Multi Agent AI Hub).
You have access to a SQLite database named **banking.db** with these tables:

• **branches** (branch_id, branch_name, address, city, state, zip_code, phone, manager_name, opened_date)
• **customers** (customer_id, first_name, last_name, email, phone, date_of_birth, ssn_last4, address, city, state, zip_code, member_since, credit_score, annual_income, branch_id, status)
• **accounts** (account_id, customer_id, account_type, account_number, routing_number, balance, interest_rate, opened_date, status)
• **transactions** (transaction_id, account_id, transaction_date, post_date, description, category, amount, transaction_type [credit/debit], balance_after, reference_number, channel)
• **loans** (loan_id, customer_id, loan_type, principal_amount, interest_rate, term_months, monthly_payment, remaining_balance, origination_date, maturity_date, status, collateral)
• **cards** (card_id, customer_id, account_id, card_type, card_network, card_number_last4, expiration_date, credit_limit, current_balance, reward_points, issued_date, status)
• **fraud_alerts** (alert_id, customer_id, account_id, card_id, alert_date, alert_type, description, amount, merchant, location, status, resolution, resolved_date)
• **customer_support** (ticket_id, customer_id, topic, subject, description, priority, status, channel, created_date, resolved_date, assigned_to)

Rules:
1. Always provide a brief natural-language summary of your findings.
2. Present tabular data in a **Markdown table**.
3. Show the SQL query you used in a ```sql code block.
4. When looking up a customer by name, use case-insensitive LIKE matching.
5. Format currency values with $ and commas.
6. Be concise, accurate, and helpful — you are a bank customer-service assistant.
7. NEVER reveal full account numbers of SSNs — show only the last 4 digits.
"""

# ---------------------------------------------------------------------------
# Intent classifier prompt
# ---------------------------------------------------------------------------

_INTENT_PROMPT = """\
You are an intent classifier for a banking customer-service agent.
Given the user's question, decide which data source(s) are needed.

Return ONLY one of these labels (no extra text):
- DATA        — the question is about specific customer data, accounts, transactions, loans, cards, fraud alerts, or support tickets (needs SQL)
- POLICY      — the question is about bank policies, fee schedules, interest rates, overdraft rules, wire transfer rules, card policies, regulatory info, or general banking rules (needs RAG over the policy document)
- BOTH        — the question needs both customer data AND policy information
- GENERAL     — a general banking question that can be answered from common knowledge without needing the database or policy document
"""


# ---------------------------------------------------------------------------
# Token capture callback
# ---------------------------------------------------------------------------

class _TokenCapture(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        for gen_list in response.generations:
            for gen in gen_list:
                if hasattr(gen, "message"):
                    add_tokens(gen.message)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Answer a banking question using SQL, RAG policy search, or both."""

    # Shared LLM for intent classification
    llm = get_chat_llm(temperature=0.0, max_tokens=20, name="banking-intent-classifier")

    # ── Step 1: Classify intent ─────────────────────────────────
    intent_response = await llm.ainvoke([
        SystemMessage(content=_INTENT_PROMPT),
        HumanMessage(content=query),
    ])
    add_tokens(intent_response)

    intent = intent_response.content.strip().upper()
    # Normalise — accept partial matches
    if "BOTH" in intent:
        intent = "BOTH"
    elif "DATA" in intent:
        intent = "DATA"
    elif "POLICY" in intent:
        intent = "POLICY"
    else:
        intent = "BOTH"  # default to both when unsure

    logger.info("Banking agent intent: %s for query: %s", intent, query[:80])

    # ── Step 2: Execute the appropriate pipeline(s) ─────────────
    tasks = []
    if intent in ("DATA", "BOTH"):
        tasks.append(("data", _query_sql(query)))
    if intent in ("POLICY", "BOTH"):
        tasks.append(("policy", _query_policy(query)))
    if intent == "GENERAL":
        tasks.append(("policy", _query_policy(query)))  # policy RAG as fallback

    results = await asyncio.gather(
        *[t for _, t in tasks],
        return_exceptions=True,
    )

    # ── Step 3: Combine results ─────────────────────────────────
    sections = []
    for (label, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error("Banking sub-task '%s' failed: %s", label, result)
            sections.append(f"⚠ {label} lookup encountered an error: {result}")
        else:
            sections.append(result)

    if len(sections) == 1:
        return sections[0]

    combined = "\n\n---\n\n".join(sections)
    return combined


# ---------------------------------------------------------------------------
# SQL sub-agent
# ---------------------------------------------------------------------------

async def _query_sql(query: str) -> str:
    """Run a natural-language SQL query against the banking database."""
    llm = get_chat_llm(temperature=0.0, name="banking-sql-llm")

    toolkit = SQLDatabaseToolkit(db=_db, llm=llm)

    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="openai-tools",
        handle_parsing_errors=True,
        prefix=_SQL_PREFIX,
    )

    result = await agent_executor.ainvoke(
        {"input": query},
        config={"callbacks": [_TokenCapture()]},
    )
    return result.get("output", str(result))


# ---------------------------------------------------------------------------
# Policy RAG sub-agent
# ---------------------------------------------------------------------------

async def _query_policy(query: str) -> str:
    """Search the bank policy index and return a grounded answer."""
    vectorstore = get_vectorstore(_BANK_INDEX_NAME)

    llm = get_chat_llm(temperature=0.2, name="banking-policy-llm")

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(),
        return_source_documents=True,
    )

    result = await qa_chain.ainvoke(
        {"query": f"Based on the Enso National Bank policy handbook: {query}"},
        config={"callbacks": [_TokenCapture()]},
    )
    answer = result.get("result", str(result))

    # Append citations
    source_docs = result.get("source_documents", [])
    if source_docs:
        seen: set[str] = set()
        citations: list[str] = []
        for i, doc in enumerate(source_docs, 1):
            meta = doc.metadata or {}
            title = (
                meta.get("title")
                or meta.get("source")
                or meta.get("chunk_id")
                or meta.get("id")
                or f"Document {i}"
            )
            if title in seen:
                continue
            seen.add(title)
            parts = [f"**[{len(citations) + 1}]** {title}"]
            page = meta.get("page") or meta.get("page_number")
            if page is not None:
                parts.append(f"Page: {page}")
            citations.append(" — ".join(parts))

        if citations:
            answer += "\n\n---\n**Policy Citations:**\n" + "\n".join(citations)

    return answer
