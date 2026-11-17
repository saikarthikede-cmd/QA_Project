# QA Project — AI Testing & Document Understanding Suite

A modular collection of FastAPI-based AI applications designed for document intelligence, retrieval-augmented generation (RAG), and structured evaluation. Built specifically for QA engineers, evaluators, and product teams to test LLM robustness, grounding, and edge-case handling.

---

## ⚡ Quick Start with `uv`

This repository uses [`uv`](https://docs.astral.sh/uv/) for fast, deterministic dependency and environment management.

### 1. Configure API Keys (Optional but Recommended)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Add your API key(s) for any supported provider:
```env
GROQ_API_KEY=gsk_your_key_here
# or OPENAI_API_KEY=sk-...
# or GEMINI_API_KEY=AIza...
# or ANTHROPIC_API_KEY=sk-ant-...
# or CODEVECTOR_API_KEY=...
```

> **Automatic Modal Bypass:** When an API key is set in `.env`, the browser modal is automatically bypassed on load!
>
> **Round-Robin & Failover:** You can provide multiple comma-separated keys (`key1, key2, key3`). The system automatically distributes requests round-robin and fails over to the next key if one hits rate limits (429) or high demand spikes (503).

---

### 2. Run the Applications

#### Option A: Run All Apps + Dashboard
```bash
uv run all
```
Or directly:
```bash
uv run python run_all.py
```

This concurrently launches the unified portal and all 6 apps:
| Service | Port | Description |
|---|---|---|
| **Portal Dashboard** | `http://localhost:8000` | Unified landing page & status monitor |
| **App 1: Resume Screener** | `http://localhost:8001` | Semantic candidate ranking against job descriptions |
| **App 2: Doc Diff Analyzer** | `http://localhost:8002` | Redline comparison & page-level change evidence |
| **App 3: FAQ Generator** | `http://localhost:8003` | RAG Q&A generator with citations & live chat |
| **App 4: Report Agent** | `http://localhost:8004` | Structured 5-section executive report generator |
| **App 5: Policy Triage** | `http://localhost:8005` | Support ticket triage agent with 4 tool calls |
| **App 6: Data Analyst** | `http://localhost:8006` | Multi-turn conversational data reasoning |

#### Option B: Run a Single App (e.g., App 3)
```bash
uv run app 3
```
Or directly:
```bash
uv run python run.py 3
```
The selected app will start immediately on its assigned port (`http://localhost:8003` for App 3).

---

## 🤖 Supported AI Providers

All apps use a unified LLM layer in `shared/` that supports 5 providers:

1. **Groq** (`llama-3.3-70b-versatile`) — Ultra-fast inference.
2. **OpenAI** (`gpt-4o-mini`) — Standard OpenAI completions and tool-calling.
3. **Google Gemini** (`gemini-flash-latest` / `gemini-flash-lite-latest`) — Dynamic alias automatically routing to Google's latest Flash or Flash-Lite model release.
4. **Claude / Anthropic** (`claude-3-5-sonnet-20241022`) — Advanced reasoning via `langchain-anthropic`.
5. **CodeVector** (`kimi-k-2-7-code`) — Integrated coding gateway from `.codevector.json`.

### Comma-Separated Key Rotation & Failover
You can paste or configure comma-separated keys in `.env` or in the UI prompt:
```env
GROQ_API_KEY=gsk_key1, gsk_key2, gsk_key3
```
- **Load Balancing:** Requests alternate between keys across turns.
- **Auto-Failover:** If `key1` returns HTTP 429 (rate limit) or HTTP 503 (server overloaded), the client immediately re-invokes with `key2` without failing the user request.

---

## 📁 Repository Structure

```text
QA_Project/
├── app3_faq_generator/       # App 3: PDF upload, RAG Q&A, FAQ generation, live chat
│   ├── main.py               # FastAPI backend with search tool and backoff
│   └── static/index.html     # Modern dark-mode UI with chips, citations, PDF export
├── src/
│   ├── portal/               # Unified dashboard serving port 8000
│   │   ├── main.py           # Health checks and status polling
│   │   └── static/index.html # Side-nav dashboard with iframe app runner
│   └── qa_project/           # CLI package entrypoints
│       ├── run.py            # Command for `uv run app <id>`
│       └── run_all.py        # Command for `uv run all`
├── shared/                   # Core shared libraries across apps
│   ├── llm_client.py         # Multi-provider client, round-robin, .env auto-loader
│   ├── llm_agent.py          # Battle-tested tool-calling agent loop
│   ├── pdf_utils.py          # PDF parsing, semantic chunking & local vector indexing
│   ├── errors.py             # Standardized HTTP error mapping & provider translation
│   └── static/key_modal.js   # Dynamic provider picker & session key manager
├── scripts/                  # Helper utilities (PDF generation, benchmarks)
├── tests/                    # Comprehensive pytest test suite
│   ├── test_apps.py          # Integration and regression tests
│   ├── test_llm_client.py    # Multi-provider, round-robin & failover tests
│   └── test_app3_comprehensive.py # Deep edge-case validation for App 3
├── pyproject.toml            # Project metadata, dependencies & uv commands
├── .codevector.json          # CodeVector gateway configuration
├── .env.example              # Environment variables template
└── README.md                 # Project documentation
```

---

## 🔎 About the Portal (`src/portal/`)

### Is the Portal Required?
- **For individual apps (e.g., `uv run app 3`):** No. Each app (1 to 6) is completely self-contained with its own UI, server, and API endpoints. App 3 runs directly on port 8003 without the portal.
- **For running the full suite (`uv run all`):** The portal runs on port 8000 and provides a single, unified view with live status monitoring (`/api/status`) of all 6 services.
- **Location:** The portal is cleanly organized inside `src/portal/`, keeping the repository root uncluttered.

---

## 🧪 Testing

Run all unit and integration tests with `uv`:

```bash
uv run pytest
```

Run tests specifically for App 3 and the LLM layer:

```bash
uv run pytest tests/test_llm_client.py tests/test_apps.py -k app3 tests/test_app3_comprehensive.py -v
```

---

## 🎯 QA Evaluation Scenarios for App 3

1. **Happy Path Generation:** Upload `test.pdf` or any multi-page PDF manual and click **⚡ Generate FAQs**. Verify 12 distinct Q&A pairs covering major sections with page citations.
2. **Duplicate Avoidance:** Click **+ Generate More**. Verify that new questions do not duplicate any of the initial questions.
3. **Targeted Regeneration:** Click **↺ Regenerate** on any card. Verify only that single card updates with a newly generated Q&A pair.
4. **CRUD Deletion:** Click **✕ Delete** on individual cards. Verify the counter decrements correctly and the array remains intact.
5. **In-Document Citations:** Ask in-document questions in the chat (e.g., *"What is the standard settlement timeline?"*). Verify exact factual accuracy and verified page tags.
6. **Adversarial / Out-of-Scope:** Ask out-of-scope questions (e.g., *"Does SmartPay support Dogecoin?"*). Verify the agent answers that the information is not found in the document with empty citations `[]`.
