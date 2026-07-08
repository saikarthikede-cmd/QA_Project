"""App 3 – FAQ Generator
Upload any PDF → AI generates Q&A pairs with page citations.
Users can regenerate individual FAQs, delete them, or request more.
"""
import sys, json, re
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.llm_client import SetKeyRequest, resolve_model, validate_key
from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, is_grounded, retrieve

app = FastAPI(title="App 3 – FAQ Generator")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.mount("/shared-static", StaticFiles(directory=Path(__file__).parent.parent / "shared" / "static"), name="shared_static")

client = None
provider = None


@app.post("/api/set-key")
def set_key(body: SetKeyRequest):
    global client, provider
    try:
        client, provider = validate_key(body.provider, body.api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


_state: dict = {"chunks": [], "filename": "", "faqs": []}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

COVERAGE_QUERIES = [
    "main purpose overview introduction background",
    "key requirements rules conditions eligibility",
    "process steps how to procedure workflow",
    "definitions terminology glossary meaning",
    "exceptions limitations restrictions exclusions",
    "costs fees pricing payment",
    "contact support help escalation",
    "timeline deadlines dates duration",
]


class RegenerateRequest(BaseModel):
    index: int


class AskRequest(BaseModel):
    question: str


def _parse_faq_list(content: str) -> List[dict]:
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)

    def _try(raw: str):
        try:
            return json.loads(raw)
        except Exception:
            pass
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
        except Exception:
            return None

    # Accept either a bare array or an object wrapping one (e.g. {"faqs": [...]})
    s = content.find("[")
    parsed = _try(content[s:content.rfind("]") + 1]) if s != -1 else None
    if parsed is None:
        s = content.find("{")
        obj = _try(content[s:content.rfind("}") + 1]) if s != -1 else None
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    parsed = v
                    break
    if not isinstance(parsed, list):
        return []
    # Keep only well-formed entries so the frontend never crashes
    return [f for f in parsed if isinstance(f, dict) and f.get("question") and f.get("answer")]


def _build_faqs(avoid_questions: Optional[List[str]] = None) -> List[dict]:
    seen_texts = set()
    combined = []
    for q in COVERAGE_QUERIES:
        for r in retrieve(q, _state["chunks"], top_k=2):
            if r.chunk.text not in seen_texts:
                combined.append(r)
                seen_texts.add(r.chunk.text)

    context = build_context(combined[:16])
    avoid = ""
    if avoid_questions:
        avoid = "\n\nDo NOT generate questions already covered:\n" + "\n".join(f"- {q}" for q in avoid_questions)

    prompt = (
        f"You are a documentation expert. Generate FAQ entries from the document below.\n\n"
        f"DOCUMENT: {_state['filename']}\n"
        f"CONTEXT:\n{context}{avoid}\n\n"
        "Return a JSON array where each item has exactly:\n"
        "- question: a specific, natural question a reader would ask\n"
        "- answer: concise accurate answer from the document only (2-4 sentences)\n"
        "- page: integer page number where the answer is found\n\n"
        "Generate exactly 12 diverse Q&A pairs covering different topics across the document.\n"
        'Return ONLY a raw JSON object of the form {"faqs": [...]}, no markdown.'
    )

    response = client.chat.completions.create(
        model=resolve_model(provider, "llama-3.1-8b-instant"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    faqs = _parse_faq_list(response.choices[0].message.content.strip())
    if not faqs:
        # Retry once without forced JSON mode
        response = client.chat.completions.create(
            model=resolve_model(provider, "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        faqs = _parse_faq_list(response.choices[0].message.content.strip())
    return faqs


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
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
    _state["chunks"] = chunks
    _state["filename"] = file.filename
    _state["faqs"] = []
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


def _safe_build_faqs(avoid_questions: Optional[List[str]] = None) -> List[dict]:
    try:
        return _build_faqs(avoid_questions)
    except Exception as e:
        raise_for_groq_error(e)


@app.post("/generate")
def generate():
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    require_client(client)
    faqs = _safe_build_faqs()
    if not faqs:
        raise HTTPException(500, "Failed to generate FAQs. Try again.")
    _state["faqs"] = faqs
    return {"faqs": _state["faqs"], "filename": _state["filename"], "count": len(faqs)}


@app.post("/generate-more")
def generate_more():
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    require_client(client)
    existing_qs = [f["question"] for f in _state["faqs"]]
    new_faqs = _safe_build_faqs(avoid_questions=existing_qs)
    _state["faqs"].extend(new_faqs)
    return {"faqs": _state["faqs"], "new_count": len(new_faqs), "total": len(_state["faqs"])}


@app.post("/regenerate")
def regenerate_one(body: RegenerateRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded.")
    idx = body.index
    if idx < 0 or idx >= len(_state["faqs"]):
        raise HTTPException(400, f"Invalid index {idx}.")
    require_client(client)
    avoid = [f["question"] for i, f in enumerate(_state["faqs"]) if i != idx]
    new_faqs = _safe_build_faqs(avoid_questions=avoid)
    if not new_faqs:
        raise HTTPException(502, "The AI could not generate a replacement question. Please retry.")
    _state["faqs"][idx] = new_faqs[0]
    return {"faq": _state["faqs"][idx], "index": idx}


@app.delete("/faqs/{index}")
def delete_faq(index: int):
    if index < 0 or index >= len(_state["faqs"]):
        raise HTTPException(400, "Invalid index.")
    _state["faqs"].pop(index)
    return {"status": "removed", "total": len(_state["faqs"])}


@app.get("/faqs")
def get_faqs():
    return {"faqs": _state["faqs"], "filename": _state["filename"], "count": len(_state["faqs"])}


@app.post("/ask")
def ask(body: AskRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    results = retrieve(body.question, _state["chunks"], top_k=3)
    if not is_grounded(results):
        return {"answer": "No relevant content found in the document.", "pages": []}
    require_client(client)

    context = build_context(results)[:1200]
    prompt = (
        f"Answer the question using ONLY the retrieved context below from '{_state['filename']}'. "
        "If the answer isn't in the context, say so clearly — do not guess.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {body.question}\n\n"
        "Give a concise, accurate answer (2-4 sentences). End with the page number(s) used."
    )
    try:
        response = _ask_groq(prompt)
    except Exception as e:
        raise_for_groq_error(e)
    pages = sorted({r.chunk.page for r in results})
    return {"answer": response.choices[0].message.content.strip(), "pages": pages}


def _ask_groq(prompt: str):
    return client.chat.completions.create(
        model=resolve_model(provider, "llama-3.1-8b-instant"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

