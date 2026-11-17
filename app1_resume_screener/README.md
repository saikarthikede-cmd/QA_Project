# App 1 — Resume Screener

Upload a Job Description PDF + candidate resume PDFs. The AI scores and ranks each candidate against the JD, citing the pages where evidence was found.

## How it works

1. **Connect a key** — a popup asks for a provider (**Groq, OpenAI or Gemini**) and your own API key. The key is validated and held in server memory only.
2. **Upload** the JD, then resumes. Each PDF is text-extracted, split into ~900-character chunks (with page numbers) and embedded locally (`all-MiniLM-L6-v2`).
3. **Screen** (RAG) — per resume: run 10 fixed queries (experience, languages, cloud, databases, leadership, education, ...), keep the 8 best chunks, then ask the LLM to score it from that evidence only. The LLM may call a `search_resume_evidence` tool for anything missing. Up to 3 candidates run in parallel.
4. **Validate** — score clamped to 0-100, recommendation derived from the score (80+ Strong Match, 50-79 Possible Match, <50 Not Suitable), cited pages taken from what was actually retrieved. A candidate that fails shows **Screening Failed** (no score) and sorts last; the others are unaffected.
5. **Results + chat** — ranked cards, a downloadable PDF report, and a Q&A box (`/ask`) grounded in the JD, resumes and screening results.

Results are also compared with a **semantic score** (pure embedding similarity, no LLM). Note it is measured against the fixed screening queries, not the JD text.

## Setup & Run

Python 3.11 is what the repo targets (`requirements.txt`); 3.12 also works. Python 3.14 does **not** (no `pydantic-core` wheel).

```powershell
# one time, from the repo root
py -3.11 -m venv .venv            # or: uv venv --python 3.12 .venv
.venv\Scripts\python -m pip install -r requirements.txt

# run
cd app1_resume_screener
..\.venv\Scripts\python -m uvicorn main:app --reload --port 8001
# Open http://localhost:8001  (first start takes ~20s while the embedding model loads)
```

Or use the root launcher (needs `py -3.11`): `.\run.ps1 1`

Then pick a provider in the popup and paste your key. After a code change to `shared/`, restart the server and hard-refresh the browser (Ctrl+Shift+R) — the key-picker script is cached by the browser.

### Providers and models

| Provider | Model used | Notes |
|---|---|---|
| Groq | `llama-3.1-8b-instant` | fast, free tier has rate limits |
| OpenAI | `gpt-4o-mini` | |
| Gemini | `gemini-3.5-flash` | override with `$env:GEMINI_MODEL = "<model>"` before starting; Google retires models (2.5-flash shut down 2026-10-16) — see https://ai.google.dev/gemini-api/docs/deprecations |

A model name Google/Groq no longer serves shows up as `NotFoundError: ...` on each candidate card.

### Tuning (constants at the top of `main.py`)

- `SCREEN_WORKERS` (default 3) — candidates screened concurrently. Set to 1 if your provider rate-limits you.
- `RESUME_CONTEXT_CHARS` / `JD_CONTEXT_CHARS` — how much evidence the LLM sees.
- `MAX_UPLOAD_BYTES`, `MAX_QUESTION_CHARS` — input limits.

### Troubleshooting

- **Screening takes very long** — watch the server terminal. Each candidate logs `screen <file>: agent loop finished in Xs ...`, then `done in Xs, score=...` or `FAILED after Xs: <error>`. Per-call timeout is 45s with 1 retry. Slow calls usually mean a slow/rate-limited provider; try Groq or `SCREEN_WORKERS = 1`.
- **"Screening Failed" on every card** — the card shows the real provider error (e.g. `NotFoundError` = wrong model, `RateLimitError`, ...).
- **New provider button missing** — hard refresh (Ctrl+Shift+R).

## Endpoints

- `POST /upload-jd` — upload the job description PDF
- `POST /upload-resume` — upload one or more candidate resumes
- `DELETE /resumes/{filename}` — remove a loaded resume
- `GET /state` — current JD, loaded resumes and last results (the page uses this to restore itself after a refresh)
- `POST /api/set-key` — choose provider (groq / openai / gemini) and validate the key
- `POST /screen` — score all loaded resumes against the JD (runs up to `SCREEN_WORKERS` candidates in parallel)
- `POST /ask` — follow-up question about the JD, resumes, or screening results

## QA Checklist

- [ ] Upload non-PDF file → rejected with error
- [ ] Scanned/image PDF → clear error, app stays usable
- [ ] Resume upload blocked until JD is uploaded
- [ ] Duplicate resume filename rejected
- [ ] Every result includes `score`, `recommendation`, `matched_skills`, `missing_skills`, `cited_pages`
- [ ] Scores sort highest-first
- [ ] Candidate whose AI call fails shows "Screening Failed" (score —), sorts last, and the others still show
- [ ] Refresh the page after uploading → JD, resumes and last results reappear
- [ ] Filename with a quote or `<` (e.g. `Bob's <CV>.pdf`) uploads, shows correctly, and can be removed
- [ ] Re-uploading the JD or adding/removing a resume clears old results and chat
- [ ] A renamed `.txt` saved as `.pdf` is rejected (400, "not a valid PDF")
- [ ] Recommendation always matches the score band (80+/50-79/<50)
- [ ] Each of Groq, OpenAI and Gemini keys can be entered and used to screen (Gemini button visible after a hard refresh)
- [ ] Invalid key → clear "rejected this key" message; app stays usable

## Automated tests

```powershell
.venv\Scripts\python -m pytest tests/test_app1_resume_screener.py -q   # App 1 only
.venv\Scripts\python -m pytest tests -q                                # everything
```
