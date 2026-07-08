# App 1 — Resume Screener

Upload a Job Description PDF + candidate resume PDFs. The AI scores and ranks each candidate against the JD, citing the pages where evidence was found.

## Run

```powershell
cd app1_resume_screener
py -3.11 -m uvicorn main:app --reload --port 8001
# Open http://localhost:8001
```

Or use the root launcher:

```powershell
.\run.ps1 1
```

## Endpoints

- `POST /upload-jd` — upload the job description PDF
- `POST /upload-resume` — upload one or more candidate resumes
- `DELETE /resumes/{filename}` — remove a loaded resume
- `POST /screen` — score all loaded resumes against the JD
- `POST /ask` — follow-up question about the JD, resumes, or screening results

## QA Checklist

- [ ] Upload non-PDF file → rejected with error
- [ ] Scanned/image PDF → clear error, app stays usable
- [ ] Resume upload blocked until JD is uploaded
- [ ] Duplicate resume filename rejected
- [ ] Every result includes `score`, `recommendation`, `matched_skills`, `missing_skills`, `cited_pages`
- [ ] Scores sort highest-first
