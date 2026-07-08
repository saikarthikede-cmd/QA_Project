# QA Demo Suite — 6 PDF-Grounded AI Apps

A collection of FastAPI demos showing different RAG and agent patterns over uploaded PDFs. Every answer is grounded in the uploaded document(s); no web search or outside knowledge is used.

## Setup

Requires **Python 3.11** (`py -3.11` must work on Windows).

```powershell
py -3.11 -m pip install -r requirements.txt
```

**No `.env` file, no API key setup, nothing to configure before running.**
Each app prompts the user for their own key the moment its page loads — a
popup asks them to pick a provider (Groq or OpenAI) and paste their key,
validates it against that provider's real API, and only then unlocks the
rest of the page. The key is held in memory for that server process only
(never written to disk); a fresh page load always asks again.

## Run any app

```powershell
.\run.ps1 1   # App 1 — Resume Screener       → http://localhost:8001
.\run.ps1 2   # App 2 — Document Diff         → http://localhost:8002
.\run.ps1 3   # App 3 — FAQ Generator         → http://localhost:8003
.\run.ps1 4   # App 4 — Report Summarizer     → http://localhost:8004
.\run.ps1 5   # App 5 — Policy Triage         → http://localhost:8005
.\run.ps1 6   # App 6 — Data Analyst          → http://localhost:8006
```

Or run manually:

```powershell
cd app1_resume_screener
py -3.11 -m uvicorn main:app --reload --port 8001
```

## The 6 Apps

| # | App | Port | What it does |
|---|-----|------|-------------|
| 1 | Resume Screener | 8001 | Upload a JD + resumes → AI scores and ranks each candidate with citations |
| 2 | Document Diff Analyzer | 8002 | Upload two PDFs → cross-document comparison with added/removed/modified changes |
| 3 | FAQ Generator | 8003 | Upload any PDF → generates editable Q&A pairs with page citations |
| 4 | Report Summarizer | 8004 | Agent extracts a structured report with page citations |
| 5 | Policy Triage | 8005 | Ticket + policy PDF → agent decides escalate/auto-resolve and drafts a reply |
| 6 | Data Analyst | 8006 | Data questions → retrieve numbers → sandboxed Python compute → result |

## Tech Stack

- **Backend**: FastAPI + Python 3.11
- **PDF parsing**: pypdf (pure Python)
- **Chunking**: 900 chars, 150 overlap, tagged with page number
- **Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (local)
- **Retrieval**: cosine similarity, top 5 chunks
- **Generation**: user-supplied Groq (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`) or OpenAI (`gpt-4o-mini`) key, entered per-app via a popup on page load
- **Scanned PDFs**: rejected with a clear error message

## Security Notes

- No API key lives on disk anywhere in this project. Users supply their own key at runtime via each app's popup, validated against the real provider API before use and held in memory only for that process.
- LLM-generated Python in App 6 runs inside a sandbox (`shared/safe_exec.py`) that forbids imports, file/network access, and dangerous builtins.
- All state is in-memory; restarting a server clears uploaded documents.

## Notes

- Python 3.14 is **not** supported — pydantic-core has no wheel for it yet. Use `py -3.11`.
- The embedding model (~80 MB) is downloaded automatically on first run.

## Development

### Generate test PDFs

```powershell
py -3.11 generate_test_pdfs.py
```

PDFs are written to `test_pdfs/`.

### Run tests

```powershell
py -3.11 -m pytest tests/
```

See `tests/` for shared utility and endpoint smoke tests.

## Docker

Each of the 6 apps builds as its own image from the shared root `Dockerfile`
(parameterized by build args); the portal builds from its own lightweight
`portal/Dockerfile` (no ML deps — it only proxies status checks).

```powershell
docker compose up -d --build
```

This starts 7 containers: `app1`..`app6` on ports 8001-8006, and `portal` on
8000 (http://localhost:8000). No `.env` file, no key setup, nothing to
configure before starting — each tester picks a provider and enters their
own key in that app's popup on first load. Inside the compose network, the
portal reaches each app by service name (`app1`, `app2`, ...) instead of
`127.0.0.1`, since each container has its own network namespace.

```powershell
docker compose down
```
