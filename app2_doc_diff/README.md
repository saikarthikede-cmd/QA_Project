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

- `GET /` — web UI
- `POST /api/set-key` — validate and activate the Groq/OpenAI/Gemini key
- `POST /upload-a` — upload document A
- `POST /upload-b` — upload document B
- `POST /analyze` — generate the diff analysis

## Response behavior

- Upload failures are explicit: non-PDF → `400`, unreadable/corrupt PDF → `422`,
  scanned/image-only PDF → `422`, file over 50 MB → `413`.
- `POST /analyze` returns `400` until both documents are uploaded, `401` when no
  API key is active, and `422` when the two documents are unrelated or no
  comparable sections can be retrieved.
- A successful analysis includes `summary`, `severity`, `change_count`,
  `added`, `removed`, `modified`, `unchanged_note`, both filenames, and
  `document_similarity`.

## Testing

```powershell
# App 2 tests only
pytest tests/test_apps.py -k app2 -q

# Full suite
pytest -q
```

## QA Checklist

- [ ] Non-PDF upload rejected
- [ ] Corrupt/unreadable PDF rejected with a clear message (not a 500)
- [ ] Scanned PDF rejected
- [ ] Analyze blocked until both documents uploaded
- [ ] Analyze blocked with a clear 401 until an API key is entered
- [ ] Diff includes `added`, `removed`, `modified`, `change_count`, `severity`
- [ ] Changes cite page numbers from both documents
- [ ] Unrelated documents return a clear "no comparable sections" error
- [ ] Uploading the same PDF twice returns a zero-change, Minor result
