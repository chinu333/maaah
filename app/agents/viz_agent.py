"""Visualization Agent — generates charts from Northwind database data.

Workflow:
1. Uses the SQL agent infrastructure (same ``SQLDatabase``) to query Northwind.
2. Converts query results into a pandas DataFrame.
3. Asks the LLM to decide chart type and to generate matplotlib code.
4. Executes the generated code in an isolated namespace and encodes the
   resulting plot as a base64 PNG embedded in Markdown.
"""

from __future__ import annotations

import io
import logging
import textwrap
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.utilities import SQLDatabase

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chart output directory (served at /static/charts/)
# ---------------------------------------------------------------------------

_CHARTS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "charts"
_CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Database setup (same Northwind DB as sql_agent)
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "northwind.db"
_DB_URI = f"sqlite:///{_DB_PATH}"
_db = SQLDatabase.from_uri(_DB_URI)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA_HINT = _db.get_table_info()


def _build_llm() -> AzureChatOpenAI:
    return get_chat_llm(temperature=0.0, name="viz-agent-llm")


# ---------------------------------------------------------------------------
# Step 1 – Generate a SQL query for the chart data
# ---------------------------------------------------------------------------

_SQL_SYSTEM = textwrap.dedent("""\
    You are an expert SQL analyst.  You will be given:
    - A Northwind SQLite database schema
    - A user request for a data visualization

    Return ONLY a single valid SQLite SELECT statement that fetches the data
    needed for the visualization.  No markdown fences, no commentary – just SQL.
    Limit results to 50 rows unless the user asks for more.
    Use square brackets for identifiers with spaces, e.g. [Order Details].
""")


async def _generate_sql(llm: AzureChatOpenAI, query: str) -> str:
    msgs = [
        SystemMessage(content=f"{_SQL_SYSTEM}\n\nDATABASE SCHEMA:\n{_SCHEMA_HINT}"),
        HumanMessage(content=query),
    ]
    resp = await llm.ainvoke(msgs)
    add_tokens(resp)
    sql = resp.content.strip()
    # Strip markdown fences if the model wraps them
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return sql


# ---------------------------------------------------------------------------
# Step 2 – Execute the SQL and return a DataFrame
# ---------------------------------------------------------------------------


def _execute_to_df(sql: str) -> pd.DataFrame:
    """Run the SQL read-only and return a pandas DataFrame."""
    import sqlite3
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA query_only = ON")
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Step 3 – Ask the LLM to write matplotlib code
# ---------------------------------------------------------------------------

_CHART_SYSTEM = textwrap.dedent("""\
    You are a Python data-visualization expert.

    You will be given:
    - A user's visualization request
    - A pandas DataFrame variable named `df` already loaded in scope
    - The columns of `df`

    Produce ONLY executable Python code (no markdown fences) that:
    1. Uses **matplotlib** (imported as `import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt`).
    2. Creates a single figure with `fig, ax = plt.subplots(figsize=(10, 6))`.
    3. Plots the appropriate chart type:
       - bar, horizontal bar, stacked bar, grouped bar
       - pie chart
       - bubble chart (scatter with size parameter)
       - line chart, area chart
       - donut chart
       - histogram
       Pick the best type for the data, or honour the user's explicit choice.
    4. Adds title, axis labels, legend if appropriate.
    5. Uses a dark background:
       `plt.style.use('dark_background')`
       with figure/axes facecolor='#161b22' and accent colors from this palette:
       ['#58a6ff','#3fb950','#f78166','#d2a8ff','#56d4dd','#f0883e','#f85149','#e3b341'].
    6. Calls `fig.tight_layout()`.
    7. Saves the figure into the BytesIO object named `buf` that is already in scope:
       `fig.savefig(buf, format='png', dpi=150, facecolor=fig.get_facecolor())`.
    8. Does NOT call `plt.show()`.

    Output ONLY the Python code.  No explanation, no fences.
""")


async def _generate_chart_code(
    llm: AzureChatOpenAI,
    query: str,
    columns: list[str],
    sample_rows: str,
) -> str:
    msgs = [
        SystemMessage(content=_CHART_SYSTEM),
        HumanMessage(content=(
            f"User request: {query}\n\n"
            f"DataFrame columns: {columns}\n\n"
            f"Sample rows (first 5):\n{sample_rows}"
        )),
    ]
    resp = await llm.ainvoke(msgs)
    add_tokens(resp)
    code = resp.content.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return code


# ---------------------------------------------------------------------------
# Step 4 – Execute the chart code safely
# ---------------------------------------------------------------------------


def _render_chart(code: str, df: pd.DataFrame) -> bytes:
    """Execute LLM-generated matplotlib code and return PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    exec_globals = {
        "df": df,
        "pd": pd,
        "plt": plt,
        "matplotlib": matplotlib,
        "buf": buf,
        "io": io,
    }
    exec(code, exec_globals)
    plt.close("all")

    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Generate a chart visualizing Northwind data based on the user's query."""
    llm = _build_llm()

    # Step 1 – SQL
    try:
        sql = await _generate_sql(llm, query)
        logger.info("Viz Agent SQL: %s", sql)
    except Exception as exc:
        logger.exception("Viz Agent: SQL generation failed")
        return f"**Error generating SQL:** {exc}"

    # Step 2 – Execute
    try:
        df = _execute_to_df(sql)
    except Exception as exc:
        logger.exception("Viz Agent: SQL execution failed")
        return (
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Execution error:** {exc}\n\nPlease try rephrasing your request."
        )

    if df.empty:
        return (
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            "The query returned no data to visualize."
        )

    # Step 3 – Chart code
    sample = df.head(5).to_string(index=False)
    try:
        chart_code = await _generate_chart_code(
            llm, query, list(df.columns), sample,
        )
        logger.debug("Viz Agent chart code:\n%s", chart_code)
    except Exception as exc:
        logger.exception("Viz Agent: chart code generation failed")
        return f"**Error generating chart code:** {exc}"

    # Step 4 – Render
    try:
        png_bytes = _render_chart(chart_code, df)
    except Exception as exc:
        logger.exception("Viz Agent: chart rendering failed")
        return (
            f"**Chart rendering error:** {exc}\n\n"
            f"**Generated code:**\n```python\n{chart_code}\n```\n\n"
            f"**Data preview:**\n```\n{sample}\n```"
        )

    # Step 5 – Save chart to static/charts/ and return URL
    chart_id = uuid.uuid4().hex[:12]
    chart_filename = f"chart_{chart_id}.png"
    chart_path = _CHARTS_DIR / chart_filename
    chart_path.write_bytes(png_bytes)
    logger.info("Viz Agent saved chart to %s", chart_path)

    chart_url = f"/static/charts/{chart_filename}"

    return (
        f"### 📊 Visualization\n\n"
        f"![chart]({chart_url})\n\n"
        f"**SQL used:**\n```sql\n{sql}\n```\n\n"
        f"**Data ({len(df)} rows, {len(df.columns)} columns):**\n\n"
        f"{df.head(10).to_markdown(index=False)}"
    )
