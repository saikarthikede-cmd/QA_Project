# App 6 — PDF Data Analyst Agent

Upload a PDF with tables or numbers and ask data questions. The agent retrieves the relevant data, writes Python to compute the answer, self-corrects on errors, and returns the result with a page citation.

LLM-generated Python runs inside a sandbox (`shared/safe_exec.py`) that forbids imports, file/network access, and dangerous builtins.

## Run

```powershell
cd app6_data_analyst
py -3.11 -m uvicorn main:app --reload --port 8006
# Open http://localhost:8006
```

Or use the root launcher:

```powershell
.\run.ps1 6
```

## Endpoints

- `POST /upload` — upload the data PDF
- `POST /analyze` — ask a data question

## QA Checklist

- [ ] Analysis blocked until PDF uploaded
- [ ] Agent steps panel shows retrieve + run_python calls
- [ ] Python errors trigger retries (visible in steps with retry badge)
- [ ] Final answer cites source page from PDF
- [ ] Question about data not in PDF returns honest "not found" answer
- [ ] Works on PDFs with financial tables, survey results, statistics
- [ ] Scanned PDF rejected
- [ ] Malicious code in `run_python` is blocked by the sandbox
