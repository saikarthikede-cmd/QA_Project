# App 2 — Document Diff Analyzer

Upload two PDFs. The agent retrieves paired sections by topic and identifies added, removed, and modified content with page citations.

## Run

```powershell
cd app2_doc_diff
py -3.11 -m uvicorn main:app --reload --port 8002
# Open http://localhost:8002
```

Or use the root launcher:

```powershell
.\run.ps1 2
```

## Endpoints

- `POST /upload-a` — upload document A
- `POST /upload-b` — upload document B
- `POST /analyze` — generate the diff analysis

## QA Checklist

- [ ] Non-PDF upload rejected
- [ ] Scanned PDF rejected
- [ ] Analyze blocked until both documents uploaded
- [ ] Diff includes `added`, `removed`, `modified`, `change_count`, `severity`
- [ ] Changes cite page numbers from both documents
- [ ] Unrelated documents return a clear "no comparable sections" error
