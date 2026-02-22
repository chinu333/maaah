# Ensō – Multi Agent AI Hub

A production-ready, full-stack **multi-agent application** powered by LangChain, LangGraph, LangSmith, and an MCP-compatible tool server — served via FastAPI with a professional dark-themed UI. Uses **Azure OpenAI** (GPT-4.1) with RBAC (`DefaultAzureCredential`), **Azure AI Search**, **Azure Maps**, **TomTom**, and **NASA** APIs.

---

## Highlights

- **12 specialised agents** — General, RAG, Multimodal, NASA, Weather, Traffic, SQL, Viz, CICP, IDA, FHIR, Banking
- **Inline AI quality evaluation** — every response is auto-scored for Relevance, Coherence, Fluency & Groundedness using `azure-ai-evaluation` SDK
- **LLM-based auto-routing** — a GPT-4.1 classifier analyses query + conversation history to select the right agent(s)
- **Parallel multi-agent execution** — multiple agents run concurrently via `asyncio.gather`
- **LLM connection cache** — `@lru_cache`-backed singletons for `AzureChatOpenAI`, embeddings & vectorstores eliminate per-request TCP+TLS overhead (~200-500ms savings)
- **Conversation memory** — LangGraph `MemorySaver` persists per-session history across turns
- **Token & cost tracking** — real-time input/output token counts and estimated cost displayed per response
- **LangSmith tracing** — full observability with `@traceable` decorators across all agents
- **Professional dark UI** — two-panel layout, gradient header, agent description bar, sample question pills, evaluation scorecard, code syntax highlighting (including custom HCL/Terraform grammar)
- **MCP-compatible** — every agent is exposed as an MCP tool for external orchestration

---

## Agents

| # | Agent | Description | External Services |
|---|-------|-------------|-------------------|
| 1 | **General** | General-purpose LLM assistant with conversation memory | Azure OpenAI |
| 2 | **RAG** | Retrieval-Augmented Generation over Azure AI Search index (`truist`) | Azure OpenAI, Azure AI Search |
| 3 | **Multimodal** | Image + text analysis using a vision-capable model (GPT-4.1) | Azure OpenAI (Vision) |
| 4 | **NASA** | Queries NASA public APIs — APOD, Mars Rover, Near-Earth Objects, Image Search | NASA APIs |
| 5 | **Weather** | Current conditions via Azure Maps with LLM-based location extraction | Azure Maps, Azure OpenAI |
| 6 | **Traffic** | Route & traffic info via TomTom with Azure Maps geocoding | TomTom, Azure Maps |
| 7 | **SQL** | Natural-language to SQL against the Northwind SQLite database (LangChain SQL Toolkit) | SQLite, Azure OpenAI |
| 8 | **Viz** | Data visualization — generates bar, pie, bubble, line, scatter charts from Northwind data | SQLite, matplotlib, Azure OpenAI |
| 9 | **CICP** | Car Insurance Claim Processing — RAG over CICP rules index with structured claim guidance | Azure AI Search (`cicp`), Azure OpenAI |
| 10 | **IDA** | Interior Design Agent — analyses room images and recommends furniture from RTG Products index | Azure AI Search (`rtg-products`), Azure OpenAI (Vision) |
| 11 | **FHIR** | FHIR Data Conversion Agent — converts CSV, HL7v2, CDA, free-text clinical notes into valid FHIR R4 JSON resources with SNOMED CT / LOINC / ICD-10 coding | Azure OpenAI |
| 12 | **Banking** | Banking Customer Service — queries customer accounts, transactions, loans, cards, fraud alerts & support tickets (SQLite) plus bank policy RAG (fee schedules, interest rates, overdraft rules) | SQLite, Azure AI Search (`bank`), Azure OpenAI |
| — | **Evaluator** | Inline quality evaluator (not user-routable) — auto-scores every response on 4 metrics using `azure-ai-evaluation` SDK | Azure OpenAI (judge LLM) |

---

## Request Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (Frontend)                          │
│  ┌───────────┐   ┌───────────┐   ┌─────────────────────────────┐   │
│  │ Compose   │   │ Agent     │   │ Response Panel              │   │
│  │ Panel     │──▶│ Pills     │   │ (Markdown + Charts + Code)  │   │
│  │ (textarea)│   │ (display) │   │ + Token/Cost + Eval Score   │   │
│  └─────┬─────┘   └───────────┘   └─────────────────────────────┘   │
│        │  POST /api/chat                        ▲                   │
│        │  { message, session_id, file_path }    │ JSON response     │
└────────┼────────────────────────────────────────┼───────────────────┘
         │                                        │
         ▼                                        │
┌─────────────────────────────────────────────────┴───────────────────┐
│                     FastAPI Backend (app/main.py)                    │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              /api/chat  →  chat.py route                     │   │
│  │                        │                                     │   │
│  │                        ▼                                     │   │
│  │  ┌──────────────────────────────────────────────────────┐    │   │
│  │  │        LangGraph Workflow (workflow.py)               │    │   │
│  │  │        ┌──────────────────────────┐                   │    │   │
│  │  │        │     MemorySaver          │ ◀─ thread_id =    │    │   │
│  │  │        │  (conversation history)  │    session_id     │    │   │
│  │  │        └──────────┬───────────────┘                   │    │   │
│  │  │                   │                                   │    │   │
│  │  │                   ▼                                   │    │   │
│  │  │        ┌──────────────────────┐                       │    │   │
│  │  │        │  classify_agents()   │                       │    │   │
│  │  │        │  (LLM-based routing  │                       │    │   │
│  │  │        │   + file detection   │                       │    │   │
│  │  │        │   + history context) │                       │    │   │
│  │  │        └──────────┬───────────┘                       │    │   │
│  │  │                   │ 1..N agents                       │    │   │
│  │  │                   ▼                                   │    │   │
│  │  │        ┌──────────────────────┐                       │    │   │
│  │  │        │  orchestrate_node()  │                       │    │   │
│  │  │        │  asyncio.gather()    │ ◀─ parallel calls     │    │   │
│  │  │        └──────────┬───────────┘                       │    │   │
│  │  │                   │ combined response                 │    │   │
│  │  │                   ▼                                   │    │   │
│  │  │        ┌──────────────────────┐                       │    │   │
│  │  │        │  evaluate_response() │ ◀─ inline auto-eval   │    │   │
│  │  │        │  (azure-ai-evaluation│    4 quality metrics   │    │   │
│  │  │        │   SDK — 4 evaluators │    scored 1-5          │    │   │
│  │  │        │   in parallel)       │                       │    │   │
│  │  │        └──────────┬───────────┘                       │    │   │
│  │  └──────────────────│────────────────────────────────────┘    │   │
│  └─────────────────────│────────────────────────────────────────┘   │
│                        │                                            │
│                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │           MCP Server (mcp/server.py)                        │    │
│  │           dispatch(agent_name, query, file_path, history)   │    │
│  └──────┬──────┬───────┬───────┬───────┬──────┬────┬────┬─────┘    │
│         │      │       │       │       │      │    │    │           │
│         ▼      ▼       ▼       ▼       ▼      ▼    ▼    ▼           │
│  ┌──────┐┌───┐┌─────┐┌────┐┌──────┐┌──────┐┌───┐┌───┐             │
│  │Genrl ││RAG││Multi││NASA││Weathr││Traffc││SQL││Viz│             │
│  └──┬───┘└─┬─┘└──┬──┘└──┬─┘└──┬───┘└──┬───┘└─┬─┘└─┬─┘             │
│  ┌──────┐┌───┐┌─────┐┌──────┐                                      │
│  │ CICP ││IDA││FHIR ││Bankng│                                      │
│  └──┬───┘└─┬─┘└──┬──┘└──┬──┘                                       │
│     │      │     │      │                                           │
│     ▼      ▼     ▼      ▼                                           │
│  Azure OpenAI  ·  Azure AI Search (truist, cicp, rtg, bank)        │
│  NASA APIs  ·  Azure Maps  ·  TomTom  ·  SQLite  ·  matplotlib     │
└─────────────────────────────────────────────────────────────────────┘
```

> **Cached LLM layer:** All agents share `@lru_cache`-backed singletons for
> `AzureChatOpenAI`, `AzureOpenAIEmbeddings`, and `AzureSearchVectorStore` via
> `app/utils/llm_cache.py`. This eliminates per-request TCP+TLS connection overhead
> (~200-500ms savings per request).

### Sequence (one request)

1. **Frontend** sends `POST /api/chat` with `{ message, session_id, file_path? }`
2. **Chat route** calls `run_workflow(query, file_path, session_id)`
3. **LangGraph** loads conversation history from `MemorySaver` using `thread_id = session_id`
4. **`classify_agents()`** sends the query + conversation history to a GPT-4.1 classifier that returns 1..N agent names
5. **`orchestrate_node()`** builds a history summary and calls all selected agents **in parallel** via `asyncio.gather`
6. **MCP `dispatch()`** maps agent name → tool handler → `agent.invoke(query, history=...)` (all using cached LLM connections)
7. Each **agent** calls its external API / LLM and returns a Markdown string; token usage is tracked per-call
8. Orchestrator **combines** multi-agent responses (or returns single) and **appends** the turn to memory
9. **`evaluate_response()`** runs 4 quality evaluators in parallel threads against the query + response (see [Evaluator](#inline-quality-evaluator) below)
10. **Chat route** returns `{ reply, agent, agents_called, session_id, timestamp, metadata: { token_usage, evaluation_scores } }`
11. **Frontend** renders the Markdown (with charts, code blocks, tables), highlights the called agent pills, shows token/cost pills, displays the **evaluation scorecard**, and shows response latency

---

## Project Structure

```
maaah/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry point, CORS, static files
│   ├── config.py                # Pydantic settings from .env
│   ├── models.py                # Pydantic request/response models, AgentName enum
│   ├── routes/
│   │   ├── chat.py              # POST /api/chat
│   │   ├── upload.py            # POST /api/upload
│   │   ├── health.py            # GET  /api/health
│   │   └── mcp_routes.py        # GET/POST /api/mcp/*
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── general_agent.py     # Azure OpenAI chat + memory context
│   │   ├── rag_agent.py         # Azure AI Search hybrid retrieval
│   │   ├── multimodal_agent.py  # Vision model (image + text)
│   │   ├── nasa_agent.py        # nasapy + NASA Image Library
│   │   ├── weather_agent.py     # Azure Maps weather + LLM location extraction
│   │   ├── traffic_agent.py     # TomTom routing + Azure Maps geocoding
│   │   ├── sql_agent.py         # LangChain SQL Toolkit (Northwind)
│   │   ├── viz_agent.py         # matplotlib chart generation
│   │   ├── cicp_agent.py        # Car Insurance Claim Processing (RAG)
│   │   ├── ida_agent.py         # Interior Design Agent (multimodal + RAG)
│   │   ├── fhir_agent.py        # FHIR R4 data conversion (HL7, CDA, CSV)
│   │   ├── banking_agent.py     # Banking customer service (SQL + policy RAG)
│   │   └── evaluator_agent.py   # Inline quality evaluator (azure-ai-evaluation)
│   ├── mcp/
│   │   └── server.py            # MCP-compatible tool server + dispatch
│   ├── graph/
│   │   └── workflow.py          # LangGraph orchestration + LLM classifier + MemorySaver + eval
│   └── utils/
│       ├── tracing.py           # LangSmith setup
│       ├── token_counter.py     # Request-scoped token & cost accumulator
│       ├── llm_cache.py         # @lru_cache singletons for LLM, embeddings, vectorstores
│       └── file_utils.py        # Upload helpers
├── static/
│   ├── index.html               # Two-panel dark-themed UI
│   ├── styles.css               # Executive dark theme, agent pills, eval scorecard styles
│   ├── app.js                   # Auto-orchestration, streaming, token pills, eval scorecard, HCL grammar
│   └── charts/                  # Generated chart PNGs (auto-created)
├── db/
│   └── northwind.db             # Northwind SQLite database
├── data/                        # Uploaded files (auto-created)
├── .env                         # Environment variables (not committed)
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## How to Add a New Agent

Follow these 6 steps to add a new agent to the workflow:

### Step 1: Create the agent module

Create a new file `app/agents/my_agent.py` with this structure:

```python
"""My Agent — brief description."""

from __future__ import annotations
from typing import Optional

async def invoke(query: str, *, file_path: Optional[str] = None, history: str = "", **kwargs) -> str:
    """Process the query and return a Markdown-formatted response."""
    # Your logic here — call APIs, run LLMs, etc.
    return "Agent response in Markdown"
```

> **Key:** The `invoke` function signature must be `async def invoke(query, *, file_path=None, history="", **kwargs) -> str`. The `**kwargs` ensures forward compatibility.

### Step 2: Register in `app/models.py`

Add your agent to the `AgentName` enum:

```python
class AgentName(str, Enum):
    RAG = "rag"
    # ... existing agents ...
    MY_AGENT = "my_agent"    # ← add this
    GENERAL = "general"      # keep general last (fallback)
```

### Step 3: Wire into `app/mcp/server.py`

Three changes in this file:

**a) Import your agent:**
```python
from app.agents import ..., my_agent
```

**b) Add a tool definition** to the `TOOL_DEFINITIONS` list:
```python
{
    "name": "my_agent_tool",
    "description": "What this agent does...",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The user's question."},
        },
        "required": ["query"],
    },
},
```

**c) Register the handler and mapping:**
```python
# In _TOOL_HANDLERS:
"my_agent_tool": my_agent.invoke,

# In AGENT_TO_TOOL:
"my_agent": "my_agent_tool",
```

### Step 4: Add routing in `app/graph/workflow.py`

Add your agent to `_VALID_AGENTS` and update the classifier system prompt:

```python
# Add to the valid-agents set:
_VALID_AGENTS = {"general", "rag", ..., "my_agent"}

# Update _CLASSIFIER_SYSTEM_PROMPT to include your agent's description
# so the LLM knows when to route queries to it.
```

### Step 5: Add the UI pill in `static/index.html`

Add a pill button in the `.agent-strip` div:

```html
<button class="agent-pill" data-agent="my_agent" title="My Agent – Description">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="2">
    <!-- your icon SVG path -->
  </svg>
  My Agent
</button>
```

Add a hint card in the `.hint-grid` div:

```html
<div class="hint-card"><strong>My Agent</strong><span>Short description</span></div>
```

Add a description entry in the `.agent-desc-bar` div:

```html
<span class="agent-desc-item"><b>My Agent</b> Short description</span>
```

### Step 6: Add the CSS pill style in `static/styles.css`

```css
.agent-pill.called[data-agent="my_agent"] {
  background: rgba(88,166,255,.10);
  border-color: var(--blue);
  color: var(--blue);
  box-shadow: 0 0 14px rgba(88,166,255,.18);
}
.agent-pill.called[data-agent="my_agent"] svg {
  opacity: 1;
  stroke: var(--blue);
}
```

### That's it!

After these 6 steps, restart the server. Your new agent will:
- Be auto-routed when the LLM classifier determines it's relevant
- Light up its pill in the UI when called
- Receive conversation history for context
- Run in parallel with other agents when multiple match
- Have its token usage tracked and displayed in the response footer
- Be **automatically quality-evaluated** on every response (Relevance, Coherence, Fluency, Groundedness)

---

## Inline Quality Evaluator

Every agent response is **automatically evaluated** using the [azure-ai-evaluation](https://learn.microsoft.com/en-us/azure/ai-studio/how-to/develop/evaluate-sdk) SDK. The evaluator runs as an inline post-processing step — it is **not** a routable agent and adds no user-facing routing complexity.

### How It Works

```
  Agent Response
       │
       ▼
┌─────────────────────────────────────────┐
│         evaluate_response()             │
│                                         │
│  ┌──────────┐  ┌──────────┐            │
│  │ Relevance│  │ Coherence│   run in   │
│  │ Evaluator│  │ Evaluator│   parallel │
│  └──────────┘  └──────────┘   threads  │
│  ┌──────────┐  ┌──────────┐            │
│  │ Fluency  │  │Grounded- │            │
│  │ Evaluator│  │  ness    │            │
│  └──────────┘  └──────────┘            │
│                                         │
│  Each evaluator uses GPT-4.1 as a       │
│  "judge LLM" to rate the response       │
│  on a 1─5 scale with pass/fail/reason.  │
└────────────────┬────────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Scorecard JSON              │
  │  { scores: [                 │
  │      { metric: "relevance",  │
  │        score: 4.0,           │
  │        result: "pass",       │
  │        reason: "..." },      │
  │      { metric: "coherence",  │
  │        score: 5.0, ... },    │
  │      ...                     │
  │    ],                        │
  │    overall_score: 4.3,       │
  │    overall_result: "pass"    │
  │  }                           │
  └──────────────────────────────┘
```

### Four Quality Metrics

| Metric | What It Measures | Scale | Threshold |
|--------|------------------|-------|-----------|
| **Relevance** | Does the response directly address the user's question? | 1–5 | ≥ 3 → pass |
| **Coherence** | Is the response logically structured and internally consistent? | 1–5 | ≥ 3 → pass |
| **Fluency** | Is the language natural, grammatically correct, and readable? | 1–5 | ≥ 3 → pass |
| **Groundedness** | Are claims substantiated by the provided context? | 1–5 | ≥ 3 → pass |

### Evaluation Pipeline

1. After `orchestrate_node()` returns the combined response, `run_workflow()` calls `evaluate_response(query, response)`
2. Four evaluator instances (cached via `@lru_cache`) are invoked **in parallel** using `asyncio.run_in_executor` (thread pool — the SDK evaluators are synchronous + IO-bound)
3. Each evaluator sends the query + response to GPT-4.1 as a "judge LLM" with a pre-built scoring prompt
4. Results are aggregated into a scorecard: per-metric scores (1–5) + pass/fail + AI-generated reasoning + overall average
5. The scorecard is returned in `metadata.evaluation_scores` and the frontend renders it as color-coded pills below each response card

### Frontend Scorecard

The scorecard appears below the token/cost stats as colored metric pills:
- **Green** (pass) — score ≥ 3
- **Red** (fail) — score < 3
- **Orange** (error) — evaluator failed
- **Overall badge** — average of all metrics, pushed to the right

Hover over any metric pill to see the AI-generated reasoning in a tooltip.

### Non-Blocking

Evaluation failure is **non-blocking** — if the evaluator times out or errors, the agent response is still returned normally with an empty scorecard. This ensures evaluation never degrades the user experience.

---

## Performance: LLM Connection Cache

All agents share **cached singletons** for Azure OpenAI clients and vectorstores via `app/utils/llm_cache.py`:

| Cached Resource | Function | What It Eliminates |
|----------------|----------|-------------------|
| `AzureChatOpenAI` | `get_chat_llm(temp, max_tokens, name, timeout)` | Per-request TCP + TLS handshake to Azure OpenAI (~200-500ms) |
| `AzureOpenAIEmbeddings` | `get_embeddings()` | Duplicate embedding client instantiation |
| `AzureSearchVectorStore` | `get_vectorstore(index_name)` | Repeated AI Search client setup per index |
| `DefaultAzureCredential` | `get_credential()` | Credential refresh on every call |
| `get_bearer_token_provider` | `get_token_provider()` | Token provider re-creation |

### How It Works

```python
# Before (per-request — slow):
def invoke(query):
    settings = get_settings()
    llm = AzureChatOpenAI(...)          # TCP + TLS every time
    embeddings = AzureOpenAIEmbeddings(...)  # another connection
    vectorstore = AzureSearch(...)      # yet another
    ...

# After (cached singleton — fast):
from app.utils.llm_cache import get_chat_llm, get_vectorstore

def invoke(query):
    llm = get_chat_llm()                # reuses existing connection
    vectorstore = get_vectorstore("truist")  # cached per index name
    ...
```

The cache uses Python's `@lru_cache` decorator — instances are created once on first use and reused for the lifetime of the process. Different `(temperature, max_tokens)` combinations produce separate cached instances (e.g., the classifier uses `temperature=0.0` while agents use `temperature=0.5`).

---

## Quick Start (Local)

### 1. Prerequisites

- Python 3.10+
- Azure subscription with:
  - Azure OpenAI resource (deployment: `gpt-4.1`)
  - Azure AI Search service (index: `truist`)
  - Azure Maps account
- TomTom API key (for traffic agent)
- (Optional) NASA API key from <https://api.nasa.gov>
- (Optional) LangSmith API key

### 2. Clone & configure

```bash
git clone <repo-url> maaah
cd maaah

# Create your .env from the template
cp .env.template .env
# Edit .env and fill in your keys
```

### 3. Create a virtual environment & install

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run the application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Docker

### Build & run with Docker

```bash
docker build -t enso .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data enso
```

### Build & run with Docker Compose

```bash
docker-compose up --build
```

---

## Deploy to Azure Container Apps

### Prerequisites

- Azure CLI (`az`) installed & logged in
- Docker (or Azure Container Registry build)

### Step-by-step

```bash
# 1. Create a resource group
az group create --name rg-enso --location eastus

# 2. Create an Azure Container Registry
az acr create --resource-group rg-enso --name ensoregistry --sku Basic

# 3. Log in to ACR
az acr login --name ensoregistry

# 4. Build & push the image
az acr build --registry ensoregistry --image enso:latest .

# 5. Create a Container Apps Environment
az containerapp env create \
  --name enso-env \
  --resource-group rg-enso \
  --location eastus

# 6. Deploy the container app
az containerapp create \
  --name enso-app \
  --resource-group rg-enso \
  --environment enso-env \
  --image ensoregistry.azurecr.io/enso:latest \
  --registry-server ensoregistry.azurecr.io \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    AZURE_OPENAI_ENDPOINT=<your-endpoint> \
    AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4.1 \
    AZURE_SEARCH_ENDPOINT=<your-search-endpoint> \
    AZURE_MAPS_SUBSCRIPTION_KEY=<your-key> \
    AZURE_MAPS_CLIENT_ID=<your-client-id> \
    TOMTOM_MAPS_API_KEY=<your-key> \
    NASA_API_KEY=<your-key> \
    LANGSMITH_API_KEY=<your-key> \
    LANGCHAIN_TRACING_V2=true \
    LANGCHAIN_PROJECT=enso

# 7. Get the app URL
az containerapp show \
  --name enso-app \
  --resource-group rg-enso \
  --query "properties.configuration.ingress.fqdn" \
  -o tsv
```

> **Tip:** For secrets, use `--secrets` and `--secret-volume-mount` or Azure Key Vault references instead of plain `--env-vars` in production.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Serves the web UI |
| `GET`  | `/api/health` | Health check |
| `POST` | `/api/chat` | Send a message to an agent |
| `POST` | `/api/upload` | Upload a file to `data/` |
| `GET`  | `/api/mcp/tools` | List MCP tool definitions |
| `POST` | `/api/mcp/call` | Invoke an MCP tool |

### Chat request body

```json
{
  "message": "What is the astronomy picture of the day?",
  "session_id": "web-abc123-1708300000000",
  "file_path": null
}
```

> **Note:** The `agent` field is optional. When omitted (the default), the LLM-based classifier auto-routes to the best agent(s) based on query content and conversation history. The `session_id` enables conversation memory across turns.

---

## Environment Variables

See `.env` for all configurable values. Authentication uses **`DefaultAzureCredential`** (RBAC) — no API keys needed for Azure OpenAI or AI Search.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | — | `gpt-4o` | Chat model deployment name |
| `AZURE_OPENAI_API_VERSION` | — | `2024-12-01-preview` | API version |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | — | `text-embedding-3-small` | Embedding model |
| `AZURE_SEARCH_ENDPOINT` | ✅ | — | Azure AI Search endpoint |
| `AZURE_SEARCH_INDEX_NAME` | — | `maaah-rag-index` | Search index name |
| `AZURE_MAPS_SUBSCRIPTION_KEY` | ✅ | — | Azure Maps subscription key |
| `AZURE_MAPS_CLIENT_ID` | ✅ | — | Azure Maps client ID |
| `TOMTOM_MAPS_API_KEY` | ✅ | — | TomTom API key for traffic |
| `NASA_API_KEY` | — | `DEMO_KEY` | NASA API key |
| `LANGSMITH_API_KEY` | — | — | LangSmith tracing key |
| `LANGCHAIN_TRACING_V2` | — | `true` | Enable LangSmith tracing |
| `LANGCHAIN_PROJECT` | — | `enso` | LangSmith project name |

---

## License

MIT — see [LICENSE](LICENSE).

---

> **Created By: CHINMOY C | 2026**
