"""App 5 – PDF Policy Triage Agent
Upload a policy PDF + paste a support ticket → agent retrieves relevant policy
via tool calls → decides escalate vs auto-resolve → drafts a grounded reply.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.json_repair import extract_json_object
from shared.llm_agent import run_tool_calling_agent
from shared.llm_client import SetKeyRequest, resolve_model, validate_key
from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, is_grounded, retrieve

app = FastAPI(title="App 5 – Policy Triage Agent")
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


_state: dict = {"chunks": [], "filename": "", "last_result": None, "chat_history": []}

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

_NEGATIVE_WORDS = [
    "angry", "furious", "unacceptable", "terrible", "worst", "lawsuit", "sue",
    "scam", "fraud", "disgusted", "frustrated", "ridiculous", "outraged", "horrible",
]


def run_tool(name: str, args: dict) -> str:
    if name == "retrieve_policy":
        # Truncate query to prevent the model from generating pathologically long strings
        query = args.get("query", "")[:300]
        results = retrieve(query, _state["chunks"], top_k=3)
        # No is_grounded() veto here — same reasoning as app6's retrieve_data:
        # this is an exploratory sub-query inside the agent's own reasoning
        # loop, not the final answer. The triage system prompt already
        # judges whether retrieved policy text actually supports a decision.
        if not results:
            return "No relevant policy found for this query."
        return build_context(results)[:900]

    if name == "check_sla_status":
        issue = args.get("issue_type", "general")[:50].strip().lower()
        return SLA_TABLE.get(issue, SLA_TABLE["general"])

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


class TriageRequest(BaseModel):
    ticket: str


class AskRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


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
    result = run_tool_calling_agent(
        client, model=model, initial_messages=initial_messages, tools=TOOLS, run_tool=run_tool,
        max_iterations=10, max_tool_calls_per_turn=3, max_total_tool_calls=12,
    )

    # app5's UI expects {"tool", "query", "result_preview"} per step, not the
    # executor's generic {"tool", "input", "output", "error"}.
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
        # Re-prompt for structured JSON, with the full tool-call trace still
        # in context — a single direct call, no tools, no loop.
        reprompt = result.messages + [HumanMessage(
            content="Now return your final answer as a JSON object with keys: decision, reason, draft_reply, policy_pages. No markdown, raw JSON only."
        )]
        r2 = client.bind(model=model, temperature=0, response_format={"type": "json_object"}).invoke(reprompt)
        parsed = extract_json_object(r2.content or "")

    if not parsed or "decision" not in parsed:
        parsed = {"decision": "ESCALATE",
                  "reason": "The AI response could not be parsed — escalating to a human by default.",
                  "draft_reply": "", "policy_pages": []}

    raw_pages = parsed.get("policy_pages", [])
    if isinstance(raw_pages, list):
        pages = [int(p) for p in raw_pages if str(p).strip().isdigit()]
    elif isinstance(raw_pages, str):
        pages = [int(x) for x in raw_pages.replace(",", " ").split() if x.strip().isdigit()]
    else:
        pages = []
    parsed["policy_pages"] = sorted(set(pages))
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
    context = build_context(results)[:1000] if results else "No relevant content found."

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
        response = client.bind(model=resolve_model(provider, "llama-3.1-8b-instant"), temperature=0).invoke(
            [HumanMessage(content=prompt)]
        )
    except Exception as e:
        raise_for_groq_error(e)

    answer = response.content.strip()
    pages = sorted({r.chunk.page for r in results})

    _state["chat_history"].append({"question": body.question, "answer": answer})
    _state["chat_history"] = _state["chat_history"][-10:]

    return {"answer": answer, "pages": pages}
