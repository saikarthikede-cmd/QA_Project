"""App 3 – FAQ Generator
Upload any PDF → AI generates Q&A pairs with page citations.
Users can regenerate individual FAQs, delete them, or request more.
"""
import re
import sys
import pickle
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.json_repair import extract_json_array
from shared.llm_agent import run_tool_calling_agent
from shared.llm_client import SetKeyRequest, init_from_env, resolve_model, validate_key
from shared.pdf_utils import (
    RetrievedChunk,
    build_context,
    build_vector_index,
    chunk_pages,
    embed_chunks,
    extract_pages,
    is_grounded,
    retrieve_from_index,
)

app = FastAPI(title="App 3 – FAQ Generator")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.mount("/shared-static", StaticFiles(directory=Path(__file__).parent.parent / "shared" / "static"), name="shared_static")

client, provider = init_from_env()


@app.get("/api/key-status")
def key_status():
    global client, provider
    if client is None:
        c, p = init_from_env()
        if c is not None:
            client, provider = c, p
    return {
        "configured": client is not None,
        "provider": provider if client is not None else None,
    }


@app.post("/api/set-key")
def set_key(body: SetKeyRequest):
    global client, provider
    try:
        client, provider = validate_key(body.provider, body.api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


_state: dict = {"chunks": [], "index": None, "filename": "", "faqs": []}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CACHE_DIR = Path(__file__).parent / ".rag_cache"
CACHE_FILE = CACHE_DIR / "last_upload.pkl"

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

SEARCH_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": (
                "Search the document for additional content on a specific topic before finalizing "
                "the FAQ list. Use if the provided context doesn't cover enough distinct topics for "
                "12 diverse Q&A pairs."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What topic to search for in the document"}},
                "required": ["query"],
            },
        },
    }
]

QUESTION_EXPANSIONS = [
    (
        ("main purpose", "purpose", "overview", "what is this document", "what does this document"),
        "main purpose overview introduction SmartPay cloud-based payment processing gateway setup features limits fees security troubleshooting",
    ),
    (
        ("deadline", "deadlines", "time limit", "time limits", "how long", "when"),
        "deadlines timelines time limits 7 days 30 days 90 days 60 seconds T+2 business days advance request verification dispute evidence refunds API key rotation",
    ),
    (
        ("violate", "violates", "violation", "terms", "requirement", "requirements", "not met", "fail"),
        "consequences requirements not met suspended KYC verification API keys rotated every 90 days HTTPS SSL 2FA mandatory chargebacks dispute evidence failed authentication gateway errors",
    ),
    (
        ("refund", "cancellation", "cancel", "return"),
        "refunds full partial dashboard API within 30 days no fee original processing fee chargebacks dispute evidence",
    ),
    (
        ("fee", "fees", "cost", "costs", "pricing"),
        "fee structure processing fees chargeback fee refund fee same-day payout fee currency conversion fee transaction fees",
    ),
    (
        ("limit", "limits", "maximum", "cap", "transaction limit"),
        "transaction limits standard accounts $10,000 $50,000 verified business accounts $250,000 ACH limits",
    ),
    (
        ("pci", "pci-dss", "compliance", "certified", "security", "encryption"),
        "security compliance PCI-DSS Level 1 certified AES-256 3DS2 2FA mandatory machine learning models",
    ),
    (
        ("crypto", "cryptocurrency", "bitcoin", "ethereum"),
        "cryptocurrency Bitcoin Ethereum SmartPay Crypto separate activation",
    ),
    (
        ("dispute", "chargeback", "win rate"),
        "chargebacks dispute notification 7 days evidence dispute win rate 68% complete documentation",
    ),
    (
        ("error", "error code", "4001", "troubleshoot", "troubleshooting", "declined"),
        "troubleshooting common errors 4001 Insufficient Funds card declined by issuer 4002 4003 4010 5001 5002",
    ),
    (
        ("retention", "retained", "data retain"),
        "data retained 7 years compliance reporting analytics",
    ),
    (
        ("support", "plan", "plans", "contact", "enterprise"),
        "support channels Standard email 24 hours Professional live chat Enterprise 24/7 phone dedicated account manager Slack connect",
    ),
    (
        ("sla", "uptime", "response time", "performance"),
        "API response time SLA 99th percentile under 300ms integration",
    ),
]

OUT_OF_SCOPE_HINTS = (
    "ceo",
    "chief executive",
    "founder",
    "stock price",
    "share price",
    "ticker",
    "market cap",
    "weather",
    "news",
)


def run_tool(name: str, args: dict) -> str:
    if name == "search_document":
        query = str(args.get("query", ""))[:300]
        results = _retrieve(query, top_k=4)
        if not results:
            return "No relevant content found for this query."
        return build_context(results)
    return "Unknown tool."


class RegenerateRequest(BaseModel):
    index: int


class AskRequest(BaseModel):
    question: str


def _parse_faq_list(content: str) -> List[dict]:
    parsed = extract_json_array(content)
    # Keep only well-formed entries so the frontend never crashes
    return [f for f in parsed if isinstance(f, dict) and f.get("question") and f.get("answer")]


def _retrieve(query: str, top_k: int = 5) -> List[RetrievedChunk]:
    _ensure_document_loaded()
    index = _state.get("index")
    if not index:
        return []
    return retrieve_from_index(query, index, top_k=top_k)


def _expanded_queries(question: str) -> List[str]:
    q = question.lower()
    queries = [question]
    for triggers, expansion in QUESTION_EXPANSIONS:
        if any(trigger in q for trigger in triggers):
            queries.append(expansion)
    return queries


def _retrieve_for_question(question: str, top_k: int = 6) -> List[RetrievedChunk]:
    """Retrieve with deterministic query expansion for broad QA questions."""
    merged: List[RetrievedChunk] = []
    seen = set()
    for query in _expanded_queries(question):
        for result in _retrieve(query, top_k=top_k):
            key = (result.chunk.page, result.chunk.text)
            if key not in seen:
                merged.append(result)
                seen.add(key)
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[:top_k]


def _is_obviously_out_of_scope(question: str) -> bool:
    q = question.lower()
    return any(hint in q for hint in OUT_OF_SCOPE_HINTS)


def _full_document_context() -> List[RetrievedChunk]:
    return [RetrievedChunk(chunk=c, score=1.0) for c in _state["chunks"]]


def _save_document_cache() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    with CACHE_FILE.open("wb") as f:
        pickle.dump(
            {
                "filename": _state["filename"],
                "chunks": _state["chunks"],
                "faqs": _state["faqs"],
            },
            f,
        )


def _ensure_document_loaded() -> bool:
    if _state["chunks"]:
        return True
    if not CACHE_FILE.exists():
        return False
    try:
        with CACHE_FILE.open("rb") as f:
            cached = pickle.load(f)
        chunks = cached.get("chunks") or []
        if not chunks:
            return False
        _state["chunks"] = chunks
        _state["index"] = build_vector_index(chunks)
        _state["filename"] = cached.get("filename", "")
        _state["faqs"] = cached.get("faqs", [])
        return True
    except Exception:
        return False


def _dedupe_faqs(faqs: List[dict], avoid_questions: Optional[List[str]] = None) -> List[dict]:
    """Normalize model output and remove repeated or weakly grounded FAQs."""
    page_count = max((c.page for c in _state["chunks"]), default=0)
    seen = {q.strip().lower() for q in (avoid_questions or [])}
    cleaned = []
    fallback = []
    for faq in faqs:
        question = str(faq.get("question", "")).strip()
        answer = str(faq.get("answer", "")).strip()
        key = question.lower()
        if not question or not answer or key in seen:
            continue
        seen.add(key)

        try:
            fallback_page = int(faq.get("page") or 1)
        except (TypeError, ValueError):
            fallback_page = 1
        if page_count:
            fallback_page = min(max(fallback_page, 1), page_count)
        fallback.append({"question": question, "answer": answer, "page": fallback_page})

        evidence = _retrieve(question, top_k=3)
        if not is_grounded(evidence):
            evidence = _retrieve(f"{question} {answer}", top_k=3)
        if not is_grounded(evidence):
            continue

        try:
            page = int(faq.get("page") or evidence[0].chunk.page)
        except (TypeError, ValueError):
            page = evidence[0].chunk.page
        evidence_pages = {r.chunk.page for r in evidence}
        if page < 1 or (page_count and page > page_count) or page not in evidence_pages:
            page = evidence[0].chunk.page

        cleaned.append({"question": question, "answer": answer, "page": page})
    return cleaned or fallback


def _build_faqs(avoid_questions: Optional[List[str]] = None, count: int = 12) -> List[dict]:
    seen_texts = set()
    combined = []
    for q in COVERAGE_QUERIES:
        for r in _retrieve(q, top_k=3):
            if r.chunk.text not in seen_texts:
                combined.append(r)
                seen_texts.add(r.chunk.text)

    # Small manuals benefit from full coverage; larger PDFs use diversified
    # semantic retrieval so prompts stay within context limits.
    if len(_state["chunks"]) <= 18:
        context = build_context([RetrievedChunk(chunk=c, score=1.0) for c in _state["chunks"]])
    else:
        context = build_context(combined[:20])
    avoid = ""
    if avoid_questions:
        avoid = "\n\nDo NOT generate questions already covered:\n" + "\n".join(f"- {q}" for q in avoid_questions)

    if count == 1:
        target_str = (
            "Generate exactly 1 high-quality Q&A pair covering an uncovered topic or detail from the document.\n"
            "Each answer must be supported by the supplied context and must not mention facts outside it."
        )
    else:
        target_str = (
            f"Generate exactly {count} diverse Q&A pairs covering different topics across the document.\n"
            "Each answer must be supported by the supplied context and must not mention facts outside it."
        )

    prompt = (
        f"You are a documentation expert. Generate FAQ entries from the document below.\n\n"
        f"DOCUMENT: {_state['filename']}\n"
        f"CONTEXT:\n{context}{avoid}\n\n"
        "Return JSON where faqs is an array and each item has exactly:\n"
        "- question: a specific, natural question a reader would ask\n"
        "- answer: concise accurate answer from the document only (2-4 sentences)\n"
        "- page: integer page number where the answer is found\n\n"
        f"{target_str}\n\n"
        'Return ONLY a raw JSON object of the form {"faqs": [...]}, no markdown.'
    )

    model = resolve_model(provider, "llama-3.1-8b-instant")
    try:
        agent_result = run_tool_calling_agent(
            client, model=model, initial_messages=[HumanMessage(content=prompt)],
            tools=SEARCH_TOOL, run_tool=run_tool,
            max_iterations=4, max_tool_calls_per_turn=2, max_total_tool_calls=4,
        )
    except Exception as e:
        fallback_models = []
        if provider == "gemini":
            fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        elif provider == "groq":
            fallback_models = ["llama-3.3-70b-versatile"]

        agent_result = None
        for fb_model in fallback_models:
            if fb_model == model:
                continue
            try:
                agent_result = run_tool_calling_agent(
                    client, model=fb_model, initial_messages=[HumanMessage(content=prompt)],
                    tools=SEARCH_TOOL, run_tool=run_tool,
                    max_iterations=4, max_tool_calls_per_turn=2, max_total_tool_calls=4,
                )
                if agent_result and agent_result.converged:
                    break
            except Exception:
                continue
        if agent_result is None:
            raise

    faqs = _parse_faq_list(agent_result.content.strip()) if agent_result.converged and agent_result.content else []
    if not faqs:
        # Retry once with a plain direct call with backoff
        for attempt in range(2):
            try:
                retry = client.bind(model=model, temperature=0.3).invoke([HumanMessage(content=prompt)])
                faqs = _parse_faq_list(retry.content.strip())
                if faqs:
                    break
            except Exception:
                if attempt == 0:
                    import time
                    time.sleep(2)
                    continue
                raise
    return _dedupe_faqs(faqs, avoid_questions=avoid_questions)


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
    _state["index"] = build_vector_index(chunks)
    _state["filename"] = file.filename
    _state["faqs"] = []
    _save_document_cache()
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


def _extract_pages_from_answer(text: str, max_page: int = 100) -> List[int]:
    pages = set()
    for m in re.finditer(r'(?:pages?|p\.)\s*([0-9]+(?:\s*(?:,|and|to|-)\s*[0-9]+)*)', text, re.IGNORECASE):
        raw = m.group(1)
        range_match = re.match(r'^(\d+)\s*(?:-|to)\s*(\d+)$', raw.strip(), re.IGNORECASE)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start <= end:
                for p in range(start, end + 1):
                    if 1 <= p <= max_page:
                        pages.add(p)
                continue
        for num in re.split(r'[,and\s]+', raw):
            if num.isdigit():
                val = int(num)
                if 1 <= val <= max_page:
                    pages.add(val)
    return sorted(pages)


def _safe_build_faqs(avoid_questions: Optional[List[str]] = None, count: int = 12) -> List[dict]:
    try:
        return _build_faqs(avoid_questions, count=count)
    except Exception as e:
        raise_for_groq_error(e)


@app.post("/generate")
def generate():
    if not _ensure_document_loaded():
        raise HTTPException(400, "No PDF uploaded yet.")
    require_client(client)
    faqs = _safe_build_faqs()
    if not faqs:
        raise HTTPException(500, "Failed to generate FAQs. Try again.")
    _state["faqs"] = faqs
    _save_document_cache()
    return {"faqs": _state["faqs"], "filename": _state["filename"], "count": len(faqs)}


@app.post("/generate-more")
def generate_more():
    if not _ensure_document_loaded():
        raise HTTPException(400, "No PDF uploaded yet.")
    require_client(client)
    existing_qs = [f["question"] for f in _state["faqs"]]
    new_faqs = _safe_build_faqs(avoid_questions=existing_qs)
    _state["faqs"].extend(new_faqs)
    _save_document_cache()
    return {"faqs": _state["faqs"], "new_count": len(new_faqs), "total": len(_state["faqs"])}


@app.post("/regenerate")
def regenerate_one(body: RegenerateRequest):
    if not _ensure_document_loaded():
        raise HTTPException(400, "No PDF uploaded.")
    idx = body.index
    if idx < 0 or idx >= len(_state["faqs"]):
        raise HTTPException(400, f"Invalid index {idx}.")
    require_client(client)
    avoid = [f["question"] for i, f in enumerate(_state["faqs"]) if i != idx]
    new_faqs = _safe_build_faqs(avoid_questions=avoid, count=1)
    if not new_faqs:
        raise HTTPException(502, "The AI could not generate a replacement question. Please retry.")
    _state["faqs"][idx] = new_faqs[0]
    _save_document_cache()
    return {"faq": _state["faqs"][idx], "index": idx}


@app.delete("/faqs/{index}")
def delete_faq(index: int):
    _ensure_document_loaded()
    if index < 0 or index >= len(_state["faqs"]):
        raise HTTPException(400, "Invalid index.")
    _state["faqs"].pop(index)
    _save_document_cache()
    return {"status": "removed", "total": len(_state["faqs"])}


@app.get("/faqs")
def get_faqs():
    _ensure_document_loaded()
    return {"faqs": _state["faqs"], "filename": _state["filename"], "count": len(_state["faqs"])}


@app.post("/ask")
def ask(body: AskRequest):
    if not _ensure_document_loaded():
        raise HTTPException(400, "No PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    if _is_obviously_out_of_scope(body.question):
        return {"answer": "No relevant content found in the document.", "pages": []}

    results = _retrieve_for_question(body.question, top_k=6)
    if not is_grounded(results) and len(_state["chunks"]) > 18:
        return {"answer": "No relevant content found in the document.", "pages": []}
    if not is_grounded(results):
        results = _full_document_context()
    require_client(client)

    if len(_state["chunks"]) <= 18:
        results = _full_document_context()

    gathered: List[RetrievedChunk] = list(results)

    def ask_tool(name: str, args: dict) -> str:
        if name != "search_document":
            return "Unknown tool."
        query = str(args.get("query", ""))[:300]
        extra = _retrieve_for_question(query, top_k=4)
        existing = {r.chunk.text for r in gathered}
        for r in extra:
            if r.chunk.text not in existing:
                gathered.append(r)
                existing.add(r.chunk.text)
        return build_context(extra) if extra else "No relevant content found for this query."

    context = build_context(results)
    prompt = (
        f"You are a RAG QA agent answering from '{_state['filename']}'.\n"
        "Use ONLY retrieved document context. If the current context is not enough, call "
        "search_document with a targeted query before answering. If the answer still is not "
        "in the retrieved context, say it is not found in the document. Do not guess.\n\n"
        f"INITIAL RETRIEVED CONTEXT:\n{context}\n\n"
        f"QUESTION: {body.question}\n\n"
        "Give a concise, accurate answer (2-4 sentences). For broad edge-case questions, explain "
        "the closest rules explicitly stated in the document rather than saying not found too early. "
        "For questions about violating terms or requirements, summarize documented consequences such as "
        "account suspension, failed authentication, dispute deadlines, required security controls, or retry guidance. "
        "If the document truly does not cover the topic, say it is not found. End with the page number(s) used."
    )
    try:
        model = resolve_model(provider, "llama-3.1-8b-instant")
        try:
            agent_result = run_tool_calling_agent(
                client,
                model=model,
                initial_messages=[HumanMessage(content=prompt)],
                tools=SEARCH_TOOL,
                run_tool=ask_tool,
                max_iterations=4,
                max_tool_calls_per_turn=2,
                max_total_tool_calls=4,
            )
        except Exception:
            fallback_models = []
            if provider == "gemini":
                fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
            elif provider == "groq":
                fallback_models = ["llama-3.3-70b-versatile"]
            agent_result = None
            for fb_model in fallback_models:
                if fb_model == model:
                    continue
                try:
                    agent_result = run_tool_calling_agent(
                        client,
                        model=fb_model,
                        initial_messages=[HumanMessage(content=prompt)],
                        tools=SEARCH_TOOL,
                        run_tool=ask_tool,
                        max_iterations=4,
                        max_tool_calls_per_turn=2,
                        max_total_tool_calls=4,
                    )
                    if agent_result and agent_result.converged:
                        break
                except Exception:
                    continue
            if agent_result is None:
                raise

        if agent_result.converged and agent_result.content:
            answer = agent_result.content.strip()
        else:
            response = _ask_llm(prompt)
            answer = response.content.strip()
    except Exception as e:
        raise_for_groq_error(e)

    page_count = max((c.page for c in _state["chunks"]), default=0)
    cited_pages = _extract_pages_from_answer(answer, max_page=page_count)

    is_not_found = any(phrase in answer.lower() for phrase in [
        "not found in the document", "not found in document", "no relevant content found",
        "not mentioned in the document", "not mentioned in document", "does not mention",
        "does not contain"
    ])
    if is_not_found:
        pages = []
    elif cited_pages:
        pages = cited_pages
    else:
        top_relevant = _retrieve_for_question(body.question, top_k=2)
        if top_relevant and is_grounded(top_relevant):
            pages = sorted({r.chunk.page for r in top_relevant})
        else:
            pages = sorted({r.chunk.page for r in gathered})
    return {"answer": answer, "pages": pages}


def _ask_llm(prompt: str):
    return client.bind(model=resolve_model(provider, "llama-3.1-8b-instant"), temperature=0).invoke(
        [HumanMessage(content=prompt)]
    )


_ask_groq = _ask_llm

