# MAAAH – Multi Agent App – Atlanta Hub

A production-ready, full-stack **multi-agent application** powered by LangChain, LangGraph, LangSmith, and an MCP-compatible tool server — served via FastAPI with a professional dark-themed UI. Uses **Azure OpenAI** with RBAC (`DefaultAzureCredential`), **Azure AI Search**, **Azure Maps**, **TomTom**, and **NASA** APIs.

---

## Agents

| Agent | Description |
|-------|-------------|
| **General** | General-purpose LLM assistant with conversation memory |
| **RAG** | Retrieval-Augmented Generation over Azure AI Search index (`truist`) |
| **Multimodal** | Image + text analysis using a vision-capable model (GPT-4.1) |
| **NASA** | Queries NASA public APIs — APOD, Mars Rover, Near-Earth Objects, Image Search |
| **Weather** | Current conditions via Azure Maps with LLM-based location extraction |
| **Traffic** | Route & traffic info via TomTom with Azure Maps geocoding |
| **SQL** | Natural-language to SQL against the Northwind SQLite database (LangChain SQL Toolkit) |
| **Viz** | Data visualization — generates bar, pie, bubble, line, scatter charts from Northwind data |

---

## Request Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (Frontend)                          │
│  ┌───────────┐   ┌───────────┐   ┌─────────────────────────────┐   │
│  │ Compose   │   │ Agent     │   │ Response Panel              │   │
│  │ Panel     │──▶│ Pills     │   │ (Markdown + Charts + Code)  │   │
│  │ (textarea)│   │ (display) │   └─────────────────────────────┘   │
│  └─────┬─────┘   └───────────┘                 ▲                   │
│        │  POST /api/chat                        │ JSON response     │
│        │  { message, session_id, file_path }    │                   │
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
│  │  │        │  (keyword + file     │                       │    │   │
│  │  │        │   based routing)     │                       │    │   │
│  │  │        └──────────┬───────────┘                       │    │   │
│  │  │                   │ 1..N agents                       │    │   │
│  │  │                   ▼                                   │    │   │
│  │  │        ┌──────────────────────┐                       │    │   │
│  │  │        │  orchestrate_node()  │                       │    │   │
│  │  │        │  asyncio.gather()    │ ◀─ parallel calls     │    │   │
│  │  │        └──────────┬───────────┘                       │    │   │
│  │  └──────────────────│────────────────────────────────────┘    │   │
│  └─────────────────────│────────────────────────────────────────┘   │
│                        │                                            │
│                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │           MCP Server (mcp/server.py)                        │    │
│  │           dispatch(agent_name, query, file_path, history)   │    │
│  └──────────┬──────┬───────┬───────┬───────┬──────┬─────┬─────┘    │
│             │      │       │       │       │      │     │           │
│             ▼      ▼       ▼       ▼       ▼      ▼     ▼           │
│  ┌───────┐┌────┐┌──────┐┌────┐┌───────┐┌───────┐┌───┐┌───┐        │
│  │General││RAG ││Multi ││NASA││Weather││Traffic││SQL││Viz│        │
│  │Agent  ││    ││modal ││    ││Agent  ││Agent  ││   ││   │        │
│  └───┬───┘└──┬─┘└──┬───┘└──┬─┘└───┬───┘└───┬───┘└─┬─┘└─┬─┘        │
│      │       │     │       │      │        │      │    │            │
│      ▼       ▼     ▼       ▼      ▼        ▼      ▼    ▼            │
│   Azure   Azure  Azure   NASA  Azure    TomTom  SQLite matplotlib  │
│   OpenAI  AI     OpenAI  APIs  Maps     API     (NW)  + LLM       │
│           Search (Vision)                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Sequence (one request)

1. **Frontend** sends `POST /api/chat` with `{ message, session_id, file_path? }`
2. **Chat route** calls `run_workflow(query, file_path, session_id)`
3. **LangGraph** loads conversation history from `MemorySaver` using `thread_id = session_id`
4. **`classify_agents()`** analyses query keywords + file extension → returns 1..N agent names
5. **`orchestrate_node()`** builds a history summary and calls all selected agents **in parallel** via `asyncio.gather`
6. **MCP `dispatch()`** maps agent name → tool handler → `agent.invoke(query, history=...)`
7. Each **agent** calls its external API / LLM and returns a Markdown string
8. Orchestrator **combines** multi-agent responses (or returns single) and **appends** the turn to memory
9. **Chat route** returns `{ reply, agent, agents_called, session_id, timestamp }`
10. **Frontend** renders the Markdown (with charts, code blocks, tables) and highlights the called agent pills

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
│   │   └── viz_agent.py         # matplotlib chart generation
│   ├── mcp/
│   │   └── server.py            # MCP-compatible tool server + dispatch
│   ├── graph/
│   │   └── workflow.py          # LangGraph orchestration + MemorySaver
│   └── utils/
│       ├── tracing.py           # LangSmith setup
│       └── file_utils.py        # Upload helpers
├── static/
│   ├── index.html               # Two-panel dark-themed UI
│   ├── styles.css               # Executive dark theme, agent pill styles
│   ├── app.js                   # Auto-orchestration, streaming, color cycle
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

### Step 4: Add routing keywords in `app/graph/workflow.py`

Add a keyword set and routing rule:

```python
_MY_AGENT_KEYWORDS = {
    "keyword1", "keyword2", "keyword3",
}

# Inside classify_agents(), before the fallback block:
if any(kw in q for kw in _MY_AGENT_KEYWORDS):
    agents.append("my_agent")
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
- Be auto-routed when the user's query matches your keywords
- Light up its pill in the UI when called
- Receive conversation history for context
- Run in parallel with other agents when multiple match

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
docker build -t maaah .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data maaah
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
az group create --name rg-maaah --location eastus

# 2. Create an Azure Container Registry
az acr create --resource-group rg-maaah --name maaahregistry --sku Basic

# 3. Log in to ACR
az acr login --name maaahregistry

# 4. Build & push the image
az acr build --registry maaahregistry --image maaah:latest .

# 5. Create a Container Apps Environment
az containerapp env create \
  --name maaah-env \
  --resource-group rg-maaah \
  --location eastus

# 6. Deploy the container app
az containerapp create \
  --name maaah-app \
  --resource-group rg-maaah \
  --environment maaah-env \
  --image maaahregistry.azurecr.io/maaah:latest \
  --registry-server maaahregistry.azurecr.io \
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
    LANGCHAIN_PROJECT=maaah

# 7. Get the app URL
az containerapp show \
  --name maaah-app \
  --resource-group rg-maaah \
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

> **Note:** The `agent` field is optional. When omitted (the default), the workflow auto-routes to the best agent(s) based on query keywords and file type. The `session_id` enables conversation memory across turns.

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
| `LANGCHAIN_PROJECT` | — | `maaah` | LangSmith project name |

---

## License

MIT — see [LICENSE](LICENSE).

---

> **Created By: CHINMOY C | 2026**
