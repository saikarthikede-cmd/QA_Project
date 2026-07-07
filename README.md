# QA Demo Suite — 6 PDF-Grounded AI Apps

A collection of FastAPI demos showing different RAG and agent patterns over uploaded PDFs. Every answer is grounded in the uploaded document(s); no web search or outside knowledge is used.

## Setup

Requires **Python 3.11** (`py -3.11` must work on Windows).

```powershell
py -3.11 -m pip install -r requirements.txt
```

Each app reads its own `.env` file from its own folder (not a shared root `.env`) — so running all 6 at once doesn't funnel every request through a single Groq key's rate limit. A placeholder `.env` already exists in each app folder; drop a real key into each one:

```
app1_resume_screener/.env
app2_doc_diff/.env
app3_faq_generator/.env
app4_report_agent/.env
app5_policy_triage/.env
app6_data_analyst/.env
```

Each contains:

```
GROQ_API_KEY=gsk_...
```

You can reuse the same key in all six, or use separate keys per app if you want fully independent rate limits. `app2` and `app4` also accept an optional `GROQ_MODEL=` override in their `.env`.

> The apps use Groq (`llama-3.3-70b-versatile`) for generation. All `.env` files are gitignored.

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
- **Generation**: Groq `llama-3.3-70b-versatile`
- **Scanned PDFs**: rejected with a clear error message

## Security Notes

- `.env` is ignored by Git and must never be committed.
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
