"""App 5 – PDF Policy Triage Agent
Upload a policy PDF + paste a support ticket → agent retrieves relevant policy
via tool calls → decides escalate vs auto-resolve → drafts a grounded reply.
"""
import os, sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from pydantic import BaseModel
from typing import List

from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, retrieve

app = FastAPI(title="App 5 – Policy Triage Agent")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

_state: dict = {"chunks": [], "filename": ""}

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
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/triage")
def triage(body: TriageRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No policy PDF uploaded yet.")
    if not body.ticket.strip():
        raise HTTPException(400, "Ticket text cannot be empty.")
    try:
        return _run_triage(body)
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "RateLimitError":
            raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
        import traceback
        raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


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

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Support ticket:\n\n{body.ticket}"},
    ]

    agent_steps = []
    total_tool_calls = 0
    MAX_TOOL_CALLS_PER_TURN = 3
    MAX_TOTAL_TOOL_CALLS = 12

    # Agentic loop with tool calls
    for _ in range(10):  # max 10 iterations — more tools means more turns
        if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
            break

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            if type(e).__name__ == "BadRequestError":
                # Model generated pathologically long tool arguments — fall back to final answer
                break
            raise
        msg = response.choices[0].message
        tool_calls = (msg.tool_calls or [])[:MAX_TOOL_CALLS_PER_TURN]

        # Build serializable assistant message dict
        msg_dict = {"role": "assistant", "content": msg.content}
        if tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(msg_dict)

        if not tool_calls:
            # Final answer — ask for clean JSON if needed
            content = msg.content or ""
            result = None
            # Strip markdown code fences if present
            clean = content
            if "```" in clean:
                import re
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
                if m:
                    clean = m.group(1)
            import re as _re

            def _try_json(raw: str):
                try:
                    return json.loads(raw)
                except Exception:
                    pass
                try:
                    return json.loads(_re.sub(r",\s*([}\]])", r"\1", raw))
                except Exception:
                    return None

            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start != -1:
                result = _try_json(clean[start:end])
            if not result or "decision" not in result:
                # Re-prompt for structured JSON
                messages.append({"role": "user", "content": "Now return your final answer as a JSON object with keys: decision, reason, draft_reply, policy_pages. No markdown, raw JSON only."})
                r2 = client.chat.completions.create(
                    model="llama-3.1-8b-instant", messages=messages, temperature=0,
                    response_format={"type": "json_object"},
                )
                content2 = r2.choices[0].message.content or ""
                s = content2.find("{"); e = content2.rfind("}") + 1
                result = _try_json(content2[s:e]) if s != -1 else None
            if not result or "decision" not in result:
                result = {"decision": "ESCALATE",
                          "reason": "The AI response could not be parsed — escalating to a human by default.",
                          "draft_reply": "", "policy_pages": []}
            # Ensure policy_pages is always a list of ints
            raw_pages = result.get("policy_pages", [])
            if isinstance(raw_pages, list):
                pages = [int(p) for p in raw_pages if str(p).strip().isdigit()]
            elif isinstance(raw_pages, str):
                pages = [int(x) for x in raw_pages.replace(",", " ").split() if x.strip().isdigit()]
            else:
                pages = []
            result["policy_pages"] = sorted(set(pages))
            result["agent_steps"] = agent_steps
            return result

        # Execute tool calls
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except Exception:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": "ERROR: malformed tool arguments — retry with valid JSON."})
                continue
            tool_result = run_tool(fn_name, fn_args)
            total_tool_calls += 1
            arg_preview = fn_args.get("query") or fn_args.get("issue_type") or fn_args.get("reason") or (fn_args.get("text", "")[:60])
            agent_steps.append({"tool": fn_name, "query": arg_preview, "result_preview": tool_result[:200]})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

    return {"decision": "ESCALATE", "reason": "Agent could not reach a conclusion.", "draft_reply": "", "policy_pages": [], "agent_steps": agent_steps}
