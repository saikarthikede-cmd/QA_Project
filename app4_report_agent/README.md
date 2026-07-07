# App 4 — PDF Report Summarizer Agent

Agent runs multiple retrieval passes and produces a structured report with sections such as Executive Summary, Key Themes, Data & Statistics, Recommendations, and Risks & Challenges — all cited from the PDF.

## Run

```powershell
cd app4_report_agent
py -3.11 -m uvicorn main:app --reload --port 8004
# Open http://localhost:8004
```

Or use the root launcher:

```powershell
.\run.ps1 4
```

## Endpoints

- `POST /upload` — upload the PDF
- `GET /generate-report` — streams SSE events with agent steps and the final report

## QA Checklist

- [ ] "Run Agent" blocked until PDF uploaded
- [ ] Agent log shows step-by-step progress (retrieve → generate)
- [ ] Each section cites page numbers
- [ ] Section with no relevant content says so explicitly
- [ ] Works on short (1-page) and long (100+ page) PDFs
- [ ] Scanned PDF rejected at upload
