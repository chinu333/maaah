---
markmap:
  colorFreezeLevel: 3
  maxWidth: 280
---

# 🌀 Ensō — Multi Agent AI Hub

## 📱 User Sends a Question
- From any device
  - 🖥️ Desktop Browser
  - 📱 Mobile / Tablet
- Types a question in natural language
  - _"What were Microsoft's cloud revenues?"_
  - _"Show top 10 countries by sales in a pie chart"_
  - _"I want to file a car insurance claim"_
- Can optionally attach a file
  - 📄 PDF, CSV, TXT, DOCX
  - 🖼️ Image (PNG, JPG, GIF)

## ⚡ FastAPI Backend Receives It
- Secure HTTPS endpoint
- `POST /api/chat`
- Carries the question + session ID + optional file

## 🧠 Smart Router (AI Classifier)
- GPT-4.1 reads the question
- Looks at conversation history
- Decides **which agent(s)** should answer
- Can pick **multiple agents** at once
  - _e.g. Weather + Traffic + General_

## 🤖 12 Specialized AI Agents
- Run **in parallel** when multiple are selected
- Each expert in its own domain
- **General** — Open-ended Q&A, coding, math
- **RAG** — Search company documents & policies
- **Multimodal** — Analyze images + text together
- **NASA** — Space photos, Mars rover, asteroids
- **Weather** — Live weather for any city
- **Traffic** — Routes, travel time, traffic delays
- **SQL** — Query business databases in plain English
- **Viz** — Create charts & graphs from data
- **CICP** — Process car insurance claims
- **IDA** — Interior design & furniture suggestions
- **FHIR** — Convert healthcare data to FHIR standard
- **Banking** — Customer accounts, loans, fraud alerts & bank policies

## 🔗 External Services Called
- ☁️ **Azure OpenAI** (GPT-4.1) — Powers all language tasks
- 🔍 **Azure AI Search** — Finds relevant documents
- 🗺️ **Azure Maps** — Weather & geocoding
- 🚗 **TomTom** — Traffic & routing
- 🚀 **NASA APIs** — Space data
- 🗄️ **SQLite Databases** — Business & banking data
- 📊 **Matplotlib** — Chart generation

## 💬 Response is Built
- Single agent → direct answer
- Multiple agents → combined sections
- Formatted as rich Markdown
  - Tables, code blocks, bullet points
  - Embedded chart images
  - Syntax-highlighted code

## ✅ AI Quality Evaluator Scores the Answer
- Runs automatically on **every response**
- Uses `azure-ai-evaluation` SDK
- GPT-4.1 acts as a **judge** and rates the answer
- **4 quality metrics** scored 1–5
  - 🎯 **Relevance** — Does it answer the question?
  - 🔗 **Coherence** — Is it logically structured?
  - ✍️ **Fluency** — Is the language natural?
  - 📌 **Groundedness** — Are claims supported by facts?
- Overall score calculated
  - ≥ 3/5 → ✅ Pass
  - < 3/5 → ⚠️ Needs Review

## 📊 Everything Sent Back to User
- The answer (rich Markdown)
- Which agent(s) answered
- Token usage & estimated cost
- Quality evaluation scorecard
- Response time

## 🖥️ Frontend Renders It
- Professional dark-themed UI
- **Agent pills** light up showing who answered
- **Token & cost pills** — how many tokens used, what it cost
- **Evaluation scorecard** — color-coded quality badges
  - 🟢 Green = Pass
  - 🔴 Red = Fail
  - 🟠 Orange = Error
  - Hover for AI reasoning
- Streaming text animation
- Code blocks with copy button & syntax highlighting
- Charts displayed inline

## 🔄 Conversation Memory
- Every Q&A turn is remembered
- Follow-up questions routed to the same agent
- Context preserved across the whole session
- Powered by LangGraph MemorySaver

## ⚙️ Performance Optimizations
- **Cached LLM connections** — No reconnecting to Azure on every request (~200-500ms saved)
- **Parallel agent execution** — Multiple agents run at the same time
- **Parallel evaluation** — 4 quality checks run simultaneously
- **LangSmith tracing** — Full observability for debugging & monitoring
