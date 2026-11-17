"""App 5 – PDF Policy Triage Agent
Upload a policy PDF + paste a support ticket → agent retrieves relevant policy
via tool calls → decides escalate vs auto-resolve → drafts a grounded reply.
"""
import pickle
import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.json_repair import extract_json_object
from shared.llm_agent import run_tool_calling_agent
from shared.llm_client import SetKeyRequest, init_from_env, resolve_model, validate_key
from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, is_grounded, retrieve

app = FastAPI(title="App 5 – Policy Triage Agent")
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


_state: dict = {"chunks": [], "filename": "", "last_result": None, "chat_history": []}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
CACHE_DIR = Path(__file__).parent / ".rag_cache"
CACHE_FILE = CACHE_DIR / "last_policy_upload.pkl"


def _save_policy_cache() -> None:
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        with CACHE_FILE.open("wb") as f:
            pickle.dump(
                {
                    "filename": _state.get("filename", ""),
                    "chunks": _state.get("chunks", []),
                    "last_result": _state.get("last_result"),
                    "chat_history": _state.get("chat_history", []),
                },
                f,
            )
    except Exception:
        pass


def _ensure_policy_loaded() -> bool:
    if _state.get("chunks"):
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
        _state["filename"] = cached.get("filename", "")
        _state["last_result"] = cached.get("last_result")
        _state["chat_history"] = cached.get("chat_history", [])
        return True
    except Exception:
        return False


@app.get("/session")
def get_session():
    _ensure_policy_loaded()
    return {
        "filename": _state.get("filename", ""),
        "chunks": len(_state.get("chunks", [])),
        "last_result": _state.get("last_result"),
        "chat_history": _state.get("chat_history", []),
    }


# Multi-tool agent: retrieval + three rule-based / heuristic tools the agent picks among.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_policy",
            "description": "Search the policy PDF for clauses relevant to a query. Use a SHORT, specific query (3-8 words). Returns matching text with page numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Short search query (3-8 words) describing the policy topic",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_sla_status",
            "description": "Look up the official SLA (service level agreement) response window for a given issue category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "One of: security, billing, legal, technical, general",
                    }
                },
                "required": ["issue_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_sentiment",
            "description": "Analyze the customer's tone in the ticket text to detect frustration, anger, or urgency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The ticket text (or relevant excerpt) to analyze",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Formally flag this ticket for human escalation. Call this ONLY when you have decided the ticket must be escalated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Short reason the ticket is being escalated",
                    }
                },
                "required": ["reason"],
            },
        },
    },
]

SLA_TABLE = {
    "security": "IMMEDIATE — security incidents must be escalated to the security team within 1 hour.",
    "billing": "24 hours — billing disputes must be resolved within 1 business day.",
    "legal": "IMMEDIATE — any legal matter (lawsuit, lawyer, legal threat) bypasses SLA and routes directly to Legal.",
    "technical": "48 hours — standard technical issue resolution window.",
    "general": "72 hours — standard support SLA for general inquiries.",
}

SLA_SYNONYMS = {
    "refund": "billing",
    "payment": "billing",
    "invoice": "billing",
    "subscription": "billing",
    "chargeback": "billing",
    "fraud": "security",
    "breach": "security",
    "hacked": "security",
    "hack": "security",
    "stolen": "security",
    "compromised": "security",
    "lawyer": "legal",
    "lawsuit": "legal",
    "litigation": "legal",
    "attorney": "legal",
    "court": "legal",
    "bug": "technical",
    "crash": "technical",
    "outage": "technical",
    "downtime": "technical",
}

_NEGATIVE_WORDS = [
    "angry", "furious", "unacceptable", "terrible", "worst", "lawsuit", "sue",
    "scam", "fraud", "disgusted", "frustrated", "ridiculous", "outraged", "horrible",
    "court", "lawyer", "attorney", "litigation", "police", "stolen", "breach", "threat", "hacked",
]


def run_tool(name: str, args: dict) -> str:
    if name == "retrieve_policy":
        query = args.get("query", "")[:300]
        results = retrieve(query, _state["chunks"], top_k=3)
        if not results:
            return "No relevant policy found for this query."
        return build_context(results)[:3000]

    if name == "check_sla_status":
        raw_issue = args.get("issue_type", "general")[:50].strip().lower()
        if raw_issue in SLA_TABLE:
            return SLA_TABLE[raw_issue]
        for key, category in SLA_SYNONYMS.items():
            if key in raw_issue:
                return SLA_TABLE[category]
        return SLA_TABLE["general"]

    if name == "classify_sentiment":
        text = args.get("text", "")[:500].lower()
        hits = sum(1 for w in _NEGATIVE_WORDS if w in text)
        if hits >= 2:
            return "NEGATIVE (high) — customer language indicates strong frustration or anger."
        if hits == 1:
            return "NEGATIVE (mild) — customer shows some frustration."
        return "NEUTRAL/POSITIVE — no strong negative sentiment detected."

    if name == "escalate_to_human":
        reason = args.get("reason", "Unspecified")[:300]
        return f"Ticket flagged for human escalation. Reason: {reason}"

    return "Unknown tool."


def _extract_pages_from_text(raw_pages, text_context: str = "", max_page: int = 100) -> List[int]:
    """Extract page citations from structured lists, strings, or prose text."""
    pages = set()
    upper = max_page if max_page > 0 else 9999

    if isinstance(raw_pages, (list, tuple)):
        for item in raw_pages:
            s = str(item).strip()
            range_match = re.match(r"^(\d+)\s*(?:-|to)\s*(\d+)$", s, re.IGNORECASE)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                for p in range(start, end + 1):
                    if 1 <= p <= upper:
                        pages.add(p)
            elif s.isdigit():
                val = int(s)
                if 1 <= val <= upper:
                    pages.add(val)
    elif isinstance(raw_pages, str) and raw_pages.strip():
        for m in re.finditer(r"(\d+)\s*(?:-|to)\s*(\d+)", raw_pages, re.IGNORECASE):
            start, end = int(m.group(1)), int(m.group(2))
            for p in range(start, end + 1):
                if 1 <= p <= upper:
                    pages.add(p)
        for num in re.split(r"[,and\s]+", raw_pages):
            if num.isdigit():
                val = int(num)
                if 1 <= val <= upper:
                    pages.add(val)

    if not pages and text_context:
        for m in re.finditer(r"(?:pages?|p\.)\s*([0-9]+(?:\s*(?:,|and|to|-)\s*[0-9]+)*)", text_context, re.IGNORECASE):
            raw = m.group(1)
            range_match = re.match(r"^(\d+)\s*(?:-|to)\s*(\d+)$", raw.strip(), re.IGNORECASE)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                for p in range(start, end + 1):
                    if 1 <= p <= upper:
                        pages.add(p)
                continue
            for num in re.split(r"[,and\s]+", raw):
                if num.isdigit():
                    val = int(num)
                    if 1 <= val <= upper:
                        pages.add(val)

    return sorted(pages)


class TriageRequest(BaseModel):
    ticket: str


class AskRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        mb = len(pdf_bytes) / 1024 / 1024
        raise HTTPException(413, f"File too large ({mb:.1f} MB). Maximum allowed size is 50 MB.")
    try:
        pages = extract_pages(pdf_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    chunks = chunk_pages(pages, source=file.filename)
    chunks = embed_chunks(chunks)
    _state["chunks"] = chunks
    _state["filename"] = file.filename
    _state["last_result"] = None
    _state["chat_history"] = []
    _save_policy_cache()
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/triage")
def triage(body: TriageRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No policy PDF uploaded yet.")
    if not body.ticket.strip():
        raise HTTPException(400, "Ticket text cannot be empty.")
    require_client(client)
    try:
        result = _run_triage(body)
        _state["last_result"] = result
        _state["chat_history"] = []
        _save_policy_cache()
        return result
    except Exception as e:
        raise_for_groq_error(e)


def _run_triage(body: TriageRequest):
    system = (
        f"You are a policy triage agent. Policy doc: '{_state['filename']}'.\n"
        "Steps: (1) retrieve_policy with a SHORT query (under 10 words). "
        "(2) check_sla_status with issue type. "
        "(3) classify_sentiment on ticket. "
        "(4) If escalating, call escalate_to_human with a short reason.\n"
        "Decision rules:\n"
        "- AUTO-RESOLVE when the request is clearly and fully allowed by the retrieved policy "
        "(e.g. refund requested within the policy's refund window) with no legal or security risk.\n"
        "- ESCALATE for legal threats, security/breach claims, fraud claims, "
        "requests outside policy limits, or ambiguous requests with very negative sentiment.\n"
        "Polite requests that policy clearly permits must be AUTO-RESOLVE, not escalated.\n"
        "Never invent policy. Call AT MOST 2 tools per turn.\n"
        "Final output: JSON with keys decision (ESCALATE or AUTO-RESOLVE), "
        "reason, draft_reply, policy_pages."
    )

    initial_messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"Support ticket:\n\n{body.ticket}"),
    ]

    model = resolve_model(provider, "llama-3.1-8b-instant")
    try:
        result = run_tool_calling_agent(
            client, model=model, initial_messages=initial_messages, tools=TOOLS, run_tool=run_tool,
            max_iterations=10, max_tool_calls_per_turn=3, max_total_tool_calls=12,
        )
    except Exception:
        fallback_models = []
        if provider == "gemini":
            fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        elif provider == "groq":
            fallback_models = ["llama-3.3-70b-versatile"]

        result = None
        for fb_model in fallback_models:
            if fb_model == model:
                continue
            try:
                result = run_tool_calling_agent(
                    client, model=fb_model, initial_messages=initial_messages, tools=TOOLS, run_tool=run_tool,
                    max_iterations=10, max_tool_calls_per_turn=3, max_total_tool_calls=12,
                )
                if result and result.converged:
                    break
            except Exception:
                continue
        if result is None:
            raise

    # app5's UI expects {"tool", "query", "result_preview"} per step
    agent_steps = [
        {
            "tool": s["tool"],
            "query": s["input"].get("query") or s["input"].get("issue_type") or s["input"].get("reason") or s["input"].get("text", "")[:60],
            "result_preview": s["output"][:200],
        }
        for s in result.agent_steps
    ]

    if not result.converged:
        return {"decision": "ESCALATE", "reason": "Agent could not reach a conclusion.", "draft_reply": "", "policy_pages": [], "agent_steps": agent_steps}

    parsed = extract_json_object(result.content or "")

    if not parsed or "decision" not in parsed:
        # Re-prompt for structured JSON without vendor-specific response_format constraint
        reprompt = result.messages + [HumanMessage(
            content="Now return your final answer as a raw JSON object with keys: decision (ESCALATE or AUTO-RESOLVE), reason, draft_reply, policy_pages. No markdown fences, output raw JSON only."
        )]
        try:
            r2 = client.bind(model=model, temperature=0).invoke(reprompt)
            parsed = extract_json_object(r2.content or "")
        except Exception:
            parsed = None

    if not parsed or "decision" not in parsed:
        parsed = {
            "decision": "ESCALATE",
            "reason": "The AI response could not be parsed — escalating to a human by default.",
            "draft_reply": "",
            "policy_pages": [],
        }

    page_count = max((c.page for c in _state["chunks"]), default=100)
    raw_pages = parsed.get("policy_pages", [])
    context_text = f"{parsed.get('reason', '')} {parsed.get('draft_reply', '')}"
    parsed["policy_pages"] = _extract_pages_from_text(raw_pages, text_context=context_text, max_page=page_count)
    parsed["agent_steps"] = agent_steps
    return parsed


@app.post("/ask")
def ask(body: AskRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No policy PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    results = retrieve(body.question, _state["chunks"], top_k=3)
    if not is_grounded(results) and not _state["last_result"]:
        return {"answer": "No relevant content found in the policy document.", "pages": []}
    require_client(client)
    context = build_context(results)[:3000] if results else "No relevant content found."

    triage_summary = ""
    if _state["last_result"]:
        lr = _state["last_result"]
        triage_summary = (
            f"Decision: {lr.get('decision', '')}. Reason: {lr.get('reason', '')}. "
            f"Draft reply sent: {lr.get('draft_reply', '')[:200]}"
        )

    history_text = "\n".join(
        f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in _state["chat_history"][-3:]
    )

    prompt = (
        f"You are answering follow-up questions about a policy triage for '{_state['filename']}'.\n\n"
        + (f"TRIAGE RESULT (for context):\n{triage_summary}\n\n" if triage_summary else "")
        + f"RETRIEVED POLICY EXCERPTS:\n{context}\n\n"
        + (f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else "")
        + f"QUESTION: {body.question}\n\n"
        "Answer using only the triage result and retrieved policy excerpts above. If not covered, say so. "
        "Keep it concise (2-4 sentences) and cite page numbers where relevant."
    )

    try:
        model = resolve_model(provider, "llama-3.1-8b-instant")
        response = client.bind(model=model, temperature=0).invoke(
            [HumanMessage(content=prompt)]
        )
    except Exception as e:
        raise_for_groq_error(e)

    answer = response.content.strip()
    page_count = max((c.page for c in _state["chunks"]), default=100)

    # Check if answer indicates out-of-scope or not found
    is_not_found = any(phrase in answer.lower() for phrase in [
        "not found in the policy", "not found in policy", "no relevant content found",
        "not mentioned in the policy", "not mentioned in policy", "not covered in the policy",
        "not covered by the policy", "does not mention", "does not contain", "not covered",
        "no information",
    ])

    if is_not_found:
        pages = []
    else:
        cited_pages = _extract_pages_from_text([], text_context=answer, max_page=page_count)
        if cited_pages:
            pages = cited_pages
        elif results and is_grounded(results):
            pages = sorted({r.chunk.page for r in results})
        else:
            pages = []

    _state["chat_history"].append({"question": body.question, "answer": answer})
    _state["chat_history"] = _state["chat_history"][-10:]
    _save_policy_cache()

    return {"answer": answer, "pages": pages}
