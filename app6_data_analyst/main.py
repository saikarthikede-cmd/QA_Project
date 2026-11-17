"""App 6 – PDF Data Analyst Agent
Upload a PDF with tables/numbers → ask data questions → agent extracts data,
writes Python to compute, self-corrects on failure, returns result with page citation.
"""
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import Cookie, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.llm_agent import run_tool_calling_agent
from shared.llm_client import SetKeyRequest, resolve_model, validate_key
from shared.pdf_utils import (
    build_context,
    build_vector_index,
    chunk_pages,
    embed_chunks,
    extract_pages,
    retrieve_from_index,
)
from shared.safe_exec import run_sandboxed_python

app = FastAPI(title="App 6 – PDF Data Analyst")
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
        raise HTTPException(400, str(e)) from e
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# BUG-01 FIX: Per-session state to prevent cross-contamination between users/tabs.
# Each browser session gets its own PDF index, filename, and conversation history,
# isolated by a UUID cookie. Previously a single global dict was shared across
# every request, so uploading a new PDF from any tab would wipe everyone's history.
# ---------------------------------------------------------------------------

SESSION_COOKIE = "app6_session"
_SESSION_MAX = 100  # evict oldest session when cap is reached

# Map of session_id → {"index": VectorIndex|None, "filename": str, "history": list}
_sessions: dict = {}


def _get_state(session_id: str) -> dict:
    """Return or create the session-local state dict for this session ID."""
    if session_id not in _sessions:
        # Evict the oldest session when we hit the cap to bound memory growth.
        if len(_sessions) >= _SESSION_MAX:
            oldest = next(iter(_sessions))
            _sessions.pop(oldest, None)
        _sessions[session_id] = {"index": None, "filename": "", "history": []}
    return _sessions[session_id]


MAX_RETRIES = 3

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_data",
            "description": "Search the PDF for tables, numbers, or data relevant to a query. Returns raw text chunks with page numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What data to look for"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code to compute a result from extracted data. Use only standard library + basic math. Print the final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_previous_answer",
            "description": "Look up a previous question/answer from earlier in this conversation by topic, so you don't re-derive it from scratch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Keyword(s) describing the earlier question to recall"}
                },
                "required": ["topic"],
            },
        },
    },
]


def _make_run_tool(state: dict):
    """Return a run_tool closure bound to the given per-session state.

    Previously run_tool was a module-level function reading from a single
    global _state dict, so concurrent sessions would see each other's data.
    Binding to the session-local state dict fixes that.
    """

    def run_tool(name: str, args: dict) -> str:
        if name == "retrieve_data":
            index = state.get("index")
            if index is None:
                return "No PDF indexed yet."

            # BUG-02 FIX: Use the pre-built VectorIndex (retrieve_from_index) instead
            # of retrieve(), which rebuilt the vector store from scratch on every call.
            # The index is now created once at upload time and reused across queries,
            # which avoids the per-query O(n) store construction overhead.
            results = retrieve_from_index(args["query"], index, top_k=5)

            # BUG-09 FIX: Drop chunks whose cosine similarity is too low before
            # passing them to the agent. Without this filter, near-zero-score chunks
            # were silently included, letting the LLM hallucinate answers from
            # loosely-related text. 0.10 is a conservative floor — low enough to
            # keep genuinely relevant chunks while blocking true noise.
            MIN_RETRIEVAL_SCORE = 0.10
            results = [r for r in results if r.score >= MIN_RETRIEVAL_SCORE]

            if not results:
                return "No relevant data found for this query."
            return build_context(results)

        if name == "run_python":
            return run_sandboxed_python(args["code"])

        if name == "recall_previous_answer":
            topic = args.get("topic", "").lower()
            matches = [h for h in state["history"] if topic in h["question"].lower()]
            if not matches:
                return "No matching previous answer found in this conversation."
            return "\n".join(f"Q: {m['question']}\nA: {m['answer'][:300]}" for m in matches[-2:])

        return "Unknown tool."

    return run_tool


class AnalysisRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@app.post("/upload")
async def upload(
    response: Response,
    file: UploadFile = File(...),
    session_id: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
):
    # BUG-01 FIX: Issue a new session cookie if the client doesn't have one yet.
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        mb = len(pdf_bytes) / 1024 / 1024
        raise HTTPException(413, f"File too large ({mb:.1f} MB). Maximum allowed size is 50 MB.")
    try:
        pages = extract_pages(pdf_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    chunks = chunk_pages(pages, source=file.filename)
    chunks = embed_chunks(chunks)

    # BUG-02 FIX: Build the VectorIndex once at upload time and store it in the
    # session so every retrieve_data call reuses the same in-memory index instead
    # of rebuilding it from scratch on each query.
    index = build_vector_index(chunks)

    state = _get_state(session_id)
    state["index"] = index
    state["filename"] = file.filename
    state["history"] = []

    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/reset-chat")
def reset_chat(session_id: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)):
    # BUG-01 FIX: Clear only this session's history, not a shared global.
    if session_id and session_id in _sessions:
        _sessions[session_id]["history"] = []
    return {"status": "cleared"}


# BUG-04 FIX: Make /analyze async and delegate the blocking LLM loop to a
# thread via asyncio.to_thread(). The original sync handler stalled FastAPI's
# event loop for the full duration of multi-turn LLM calls under any concurrency.
@app.post("/analyze")
async def analyze(
    body: AnalysisRequest,
    response: Response,
    session_id: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
):
    # Edge case: browser hit /analyze before the /upload response set the cookie.
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax")

    state = _get_state(session_id)
    if state.get("index") is None:
        raise HTTPException(400, "No PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    require_client(client)
    try:
        # Run the synchronous agent loop in a thread pool so the event loop
        # remains free to handle other requests during the LLM round-trips.
        return await asyncio.to_thread(_run_analysis, body, state)
    except Exception as e:
        raise_for_groq_error(e)


def _run_analysis(body: AnalysisRequest, state: dict):
    system = (
        f"You are a strict data analyst agent with access to '{state['filename']}'. "
        "This is a multi-turn conversation — you have memory of earlier questions via recall_previous_answer.\n"
        "Workflow:\n"
        "1. Use retrieve_data to find the EXACT numbers or data needed to answer the question.\n"
        "2. If this question builds on an earlier one, use recall_previous_answer to check conversation memory first.\n"
        "3. If the retrieved chunks do NOT contain the specific data requested (e.g. monthly breakdown "
        "when only annual data exists), respond IMMEDIATELY with: "
        "'I can't find this in the uploaded document.' Do NOT substitute with related data.\n"
        "4. If the exact data IS present, use run_python to compute the answer.\n"
        "5. If run_python returns an ERROR, fix the code and retry (up to 3 times).\n"
        "6. Never invent, estimate, or extrapolate numbers not explicitly in the PDF.\n"
        "7. Always cite the page number(s) where the data came from.\n"
        "8. Final answer: result + brief computation explanation + source page.\n"
        "STRICT RULE: If the question asks for data granularity that does not exist in the PDF "
        "(e.g. monthly when only quarterly exists, per-product when only category totals exist), "
        "say exactly: 'I can't find this in the uploaded document.' and stop.\n"
        # BUG-10 FIX: System prompt now says 3 to match max_tool_calls_per_turn=3 in code.
        # Previously the prompt said 2 while the code enforced 3 — a silent mismatch.
        "IMPORTANT: Call AT MOST 3 tools per turn. Do not repeat the same call."
    )

    history_context = ""
    if state["history"]:
        recent = state["history"][-3:]
        history_context = "\n\nRecent conversation:\n" + "\n".join(
            f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in recent
        )

    initial_messages = [
        SystemMessage(content=system + history_context),
        HumanMessage(content=body.question),
    ]

    def is_python_error(name: str, result: str) -> bool:
        return name == "run_python" and result.startswith("ERROR")

    # BUG-01 FIX: Pass a session-bound run_tool closure instead of the former
    # module-level function that read from the shared global _state dict.
    run_tool = _make_run_tool(state)

    result = run_tool_calling_agent(
        client,
        model=resolve_model(provider, "openai/gpt-oss-20b"),
        initial_messages=initial_messages,
        tools=TOOLS,
        run_tool=run_tool,
        max_iterations=12,
        max_tool_calls_per_turn=3,  # small models can hallucinate dozens of calls in one turn
        max_total_tool_calls=12,
        max_context_turns=4,
        is_error=is_python_error,
        max_error_retries=MAX_RETRIES,
        escalation_message="Python execution failed too many times. Provide the best answer you can from the retrieved data without running code.",
    )

    # BUG-05 FIX: Track a cumulative error count across all steps so the retry
    # badge on the frontend shows the globally correct attempt number.
    # The original code reset the counter to 0 on every non-error step, so a
    # sequence like [error, error, success, error] would display [1, 2, 0, 1]
    # instead of the correct [1, 2, —, 3].
    total_errors = 0
    for step in result.agent_steps:
        if step["error"]:
            total_errors += 1
            step["retry"] = total_errors
        else:
            step["retry"] = 0  # 0 = no badge shown for successful steps

    if result.converged:
        answer = result.content or "No answer produced."
        state["history"].append({"question": body.question, "answer": answer})
        state["history"] = state["history"][-10:]
        return {"answer": answer, "agent_steps": result.agent_steps}

    final_answer = "Agent did not converge in time. Try a simpler/more specific question."
    state["history"].append({"question": body.question, "answer": final_answer})
    # BUG-13 FIX: Apply the -10 history cap on the non-converged path too.
    # Previously the cap (state["history"][-10:]) was only applied on the
    # converged path, so non-converged turns could grow the history unboundedly.
    state["history"] = state["history"][-10:]
    return {"answer": final_answer, "agent_steps": result.agent_steps}
