"""Portal – unified dashboard for all 6 AI QA-suite apps."""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

app = FastAPI(title="AI Tools Portal")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

APPS = [
    {"id": "app1", "port": 8001, "name": "Resume Screener",      "icon": "📄", "color": "#6366f1", "desc": "Upload a job description and candidate resumes. AI ranks candidates by semantic fit and lets you ask follow-up questions."},
    {"id": "app2", "port": 8002, "name": "Doc Diff Analyzer",    "icon": "🔍", "color": "#0ea5e9", "desc": "Upload two PDF versions of a document. AI detects additions, deletions and rewrites with page-level evidence."},
    {"id": "app3", "port": 8003, "name": "FAQ Generator",        "icon": "💬", "color": "#10b981", "desc": "Upload any PDF manual or policy. AI auto-generates FAQ pairs and lets you ask custom questions via chat."},
    {"id": "app4", "port": 8004, "name": "Report Agent",         "icon": "📊", "color": "#f59e0b", "desc": "Upload a business report PDF. Agentic AI writes a full 5-section structured report with page citations."},
    {"id": "app5", "port": 8005, "name": "Policy Triage Agent",  "icon": "🛡️", "color": "#f43f5e", "desc": "Upload a support policy PDF and paste a customer ticket. Agent decides escalate vs auto-resolve using 4 tools."},
    {"id": "app6", "port": 8006, "name": "Data Analyst Agent",   "icon": "📈", "color": "#a855f7", "desc": "Upload a data CSV or PDF. Multi-turn agent runs Python computations and remembers previous answers across turns."},
]


@app.get("/")
def index():
    return FileResponse(
        Path(__file__).parent / "static" / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/status")
async def status():
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for a in APPS:
            try:
                r = await client.get(f"http://127.0.0.1:{a['port']}/")
                results[a["id"]] = "up" if r.status_code < 500 else "error"
            except Exception:
                results[a["id"]] = "down"
    return JSONResponse(results, headers={"Cache-Control": "no-store"})


@app.get("/api/apps")
def apps_list():
    return APPS
