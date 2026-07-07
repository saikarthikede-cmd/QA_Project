"""App 2 – Document Diff Analyzer  [RAG]
Embeds both documents as chunks.
Cross-retrieves corresponding sections from each document using topic queries,
then generates a diff grounded in retrieved paired evidence with page citations.
"""
import os, sys, json, re
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq

from shared.pdf_utils import chunk_pages, embed_chunks, extract_pages, retrieve

app = FastAPI(title="App 2 – Document Diff Analyzer (RAG)")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

_state: dict = {
    "doc_a": {"chunks": [], "filename": "", "page_count": 0},
    "doc_b": {"chunks": [], "filename": "", "page_count": 0},
}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Topic queries used to cross-retrieve corresponding sections from both docs
COMPARISON_TOPICS = [
    "overview purpose scope introduction",
    "pricing fees costs payments billing",
    "refund cancellation termination policy",
    "data privacy security retention storage",
    "eligibility requirements conditions rules",
    "support service level availability response time",
    "liability warranty limitations disclaimer",
    "governing law jurisdiction dispute resolution",
    "user responsibilities obligations prohibited use",
    "changes amendments updates notices",
    "benefits entitlements rewards programme",
    "deadlines timelines notice periods",
]


def _parse_json(content: str) -> dict:
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    s = content.find("{"); e = content.rfind("}") + 1
    if s == -1:
        return {}
    raw = content[s:e]
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Repair common model mistakes: trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(repaired)
    except Exception:
        return {}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


def _build_metadata(pdf_bytes: bytes, pages: list, chunks: list, filename: str) -> dict:
    total_chars = sum(len(t) for _, t in pages)
    total_words = sum(len(t.split()) for _, t in pages)
    reader_meta = {}
    try:
        from pypdf import PdfReader
        import io as _io
        info = PdfReader(_io.BytesIO(pdf_bytes)).metadata or {}
        reader_meta = {
            "author": str(info.get("/Author", "") or ""),
            "title": str(info.get("/Title", "") or ""),
            "creator": str(info.get("/Creator", "") or ""),
            "created": str(info.get("/CreationDate", "") or ""),
        }
    except Exception:
        pass
    return {
        "filename": filename,
        "file_size_kb": round(len(pdf_bytes) / 1024, 1),
        "page_count": len(pages),
        "word_count": total_words,
        "char_count": total_chars,
        "chunk_count": len(chunks),
        **reader_meta,
    }


@app.post("/upload-a")
async def upload_a(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large ({len(pdf_bytes)/1024/1024:.1f} MB). Max 50 MB.")
    try:
        pages = extract_pages(pdf_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    chunks = chunk_pages(pages, source=file.filename)
    chunks = embed_chunks(chunks)
    metadata = _build_metadata(pdf_bytes, pages, chunks, file.filename)
    _state["doc_a"] = {"chunks": chunks, "filename": file.filename, "page_count": len(pages), "metadata": metadata}
    return {"status": "ok", "filename": file.filename, "pages": len(pages), "metadata": metadata}


@app.post("/upload-b")
async def upload_b(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large ({len(pdf_bytes)/1024/1024:.1f} MB). Max 50 MB.")
    try:
        pages = extract_pages(pdf_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    chunks = chunk_pages(pages, source=file.filename)
    chunks = embed_chunks(chunks)
    metadata = _build_metadata(pdf_bytes, pages, chunks, file.filename)
    _state["doc_b"] = {"chunks": chunks, "filename": file.filename, "page_count": len(pages), "metadata": metadata}
    return {"status": "ok", "filename": file.filename, "pages": len(pages), "metadata": metadata}


@app.post("/analyze")
def analyze():
    if not _state["doc_a"]["chunks"]:
        raise HTTPException(400, "Document A not uploaded yet.")
    if not _state["doc_b"]["chunks"]:
        raise HTTPException(400, "Document B not uploaded yet.")
    try:
        return _run_analyze()
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "RateLimitError":
            raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
        import traceback
        raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


def _run_analyze():
    # RAG: for each topic, retrieve corresponding sections from BOTH documents
    comparison_blocks: List[str] = []
    for topic in COMPARISON_TOPICS:
        from_a = retrieve(topic, _state["doc_a"]["chunks"], top_k=1)
        from_b = retrieve(topic, _state["doc_b"]["chunks"], top_k=1)

        # Only include topics where both docs have relevant content (score > threshold)
        if not from_a or not from_b:
            continue
        if from_a[0].score < 0.20 and from_b[0].score < 0.20:
            continue

        pages_a = sorted({r.chunk.page for r in from_a})
        pages_b = sorted({r.chunk.page for r in from_b})
        text_a = from_a[0].chunk.text[:650] if from_a else ""
        text_b = from_b[0].chunk.text[:650] if from_b else ""

        comparison_blocks.append(
            f"[TOPIC: {topic}]\n"
            f"DOC A — {_state['doc_a']['filename']} (pages {pages_a}):\n{text_a}\n\n"
            f"DOC B — {_state['doc_b']['filename']} (pages {pages_b}):\n{text_b}"
        )

    if not comparison_blocks:
        raise HTTPException(422, "Could not retrieve comparable sections from both documents.")

    full_context = "\n\n---\n\n".join(comparison_blocks[:10])

    prompt = (
        "You are a document analyst. Below are paired sections retrieved from two documents "
        "on the same topics. Compare them and identify all meaningful differences.\n"
        "Do not say parsing failed. Do not describe your process. Return the actual comparison result.\n\n"
        f"DOCUMENT A: {_state['doc_a']['filename']}\n"
        f"DOCUMENT B: {_state['doc_b']['filename']}\n\n"
        f"PAIRED RETRIEVED SECTIONS:\n{full_context}\n\n"
        "Based ONLY on the retrieved content above, return a JSON object with:\n"
        "- summary: 2-3 sentence overall description of what changed and severity\n"
        "- severity: 'Minor', 'Moderate', or 'Major'\n"
        "- change_count: total distinct changes found\n"
        "- added: list of {content: str, location: str} — content in Doc B not in Doc A\n"
        "- removed: list of {content: str, location: str} — content in Doc A absent from Doc B\n"
        "- modified: list of {original: str, revised: str, location: str} — changed content\n"
        "- unchanged_note: what stayed the same\n\n"
        "Rules:\n"
        "- Include page numbers in every location.\n"
        "- Quote or closely paraphrase the retrieved text.\n"
        "- If there are no changes, return severity 'Minor', change_count 0, empty arrays, and explain in unchanged_note.\n"
        "- Return ONLY raw JSON."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    data = _parse_json(raw)
    if not _is_valid_analysis(data):
        repair_prompt = (
            "Your previous answer was not a valid document diff JSON object.\n"
            f"Previous answer:\n{raw[:1200]}\n\n"
            "Using the paired document sections below, return a valid JSON object with exactly these keys: "
            "summary, severity, change_count, added, removed, modified, unchanged_note.\n\n"
            f"{full_context}\n\n"
            "Return ONLY raw JSON."
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": repair_prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = _parse_json(response.choices[0].message.content.strip())
    if not _is_valid_analysis(data):
        raise HTTPException(502, "The AI returned an invalid diff analysis. Please retry; no fake result was shown.")

    # Normalize types so the frontend never crashes on unexpected shapes
    for key in ("added", "removed", "modified"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("change_count"), int):
        try:
            data["change_count"] = int(data.get("change_count", 0))
        except Exception:
            data["change_count"] = len(data["added"]) + len(data["removed"]) + len(data["modified"])
    data["doc_a"] = _state["doc_a"]["filename"]
    data["doc_b"] = _state["doc_b"]["filename"]
    data["topics_compared"] = len(comparison_blocks)
    return data


def _is_valid_analysis(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    required = {"summary", "severity", "change_count", "added", "removed", "modified", "unchanged_note"}
    if not required.issubset(data):
        return False
    summary = str(data.get("summary", "")).lower()
    return "failed to parse" not in summary and "analysis failed" not in summary

