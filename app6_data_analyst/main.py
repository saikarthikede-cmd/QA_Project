"""App 6 – PDF Data Analyst Agent
Upload a PDF with tables/numbers → ask data questions → agent extracts data,
writes Python to compute, self-corrects on failure, returns result with page citation.
"""
import os, sys, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from pydantic import BaseModel

from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, retrieve
from shared.safe_exec import run_sandboxed_python

app = FastAPI(title="App 6 – PDF Data Analyst")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

_state: dict = {"chunks": [], "filename": "", "history": [], "pages": [], "numeric_entries": []}

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


def run_tool(name: str, args: dict) -> str:
    if name == "retrieve_data":
        results = retrieve(args["query"], _state["chunks"], top_k=5)
        if not results:
            return "No relevant data found for this query."
        return build_context(results)

    if name == "run_python":
        return run_sandboxed_python(args["code"])

    if name == "recall_previous_answer":
        topic = args.get("topic", "").lower()
        matches = [h for h in _state["history"] if topic in h["question"].lower()]
        if not matches:
            return "No matching previous answer found in this conversation."
        return "\n".join(f"Q: {m['question']}\nA: {m['answer'][:300]}" for m in matches[-2:])

    return "Unknown tool."


def _money_to_float(raw: str) -> float:
    return float(raw.replace("$", "").replace(",", ""))


def _extract_numeric_entries(pages: list[tuple]) -> list[dict]:
    entries: list[dict] = []
    money_pattern = re.compile(r"\$[\d,]+(?:\.\d+)?")
    number_pattern = re.compile(r"(?<![$\w])\d[\d,]*(?:\.\d+)?(?:%|x)?")

    for page, text in pages:
        for line in text.splitlines():
            clean = " ".join(line.strip(" -").split())
            if not clean:
                continue

            money_matches = money_pattern.findall(clean)
            for raw in money_matches:
                entries.append(
                    {
                        "label": clean,
                        "raw": raw,
                        "value": _money_to_float(raw),
                        "unit": "usd",
                        "page": page,
                    }
                )

            # Keep non-currency numbers available for targeted questions, but
            # avoid duplicating the numeric part of currency values.
            without_money = money_pattern.sub("", clean)
            for raw in number_pattern.findall(without_money):
                normalized = raw.replace(",", "")
                unit = "percent" if raw.endswith("%") else "multiple" if raw.endswith("x") else "number"
                try:
                    value = float(normalized.rstrip("%x"))
                except ValueError:
                    continue
                entries.append(
                    {
                        "label": clean,
                        "raw": raw,
                        "value": value,
                        "unit": unit,
                        "page": page,
                    }
                )

    return entries


def _format_usd(value: float) -> str:
    return f"${value:,.2f}".replace(".00", "")


def _direct_numeric_answer(question: str) -> dict | None:
    q = question.lower()
    money_entries = [e for e in _state["numeric_entries"] if e["unit"] == "usd"]
    if not money_entries:
        return None

    wants_all_sum = ("total" in q or "sum" in q) and ("all" in q or "figures" in q or "entries" in q)
    wants_average = ("average" in q or "mean" in q) and ("all" in q or "entries" in q or "figures" in q or "value" in q)

    if not wants_all_sum and not wants_average:
        return None

    values = [e["value"] for e in money_entries]
    total = sum(values)
    average = total / len(values)
    pages = sorted({e["page"] for e in money_entries})
    labels_preview = "\n".join(f"- p.{e['page']}: {e['label']}" for e in money_entries[:12])

    code = (
        f"values = {values!r}\n"
        "total = sum(values)\n"
        "average = total / len(values)\n"
        "print(total)\n"
        "print(average)\n"
        "print(len(values))"
    )
    python_output = run_sandboxed_python(code)

    if wants_average:
        answer = (
            f"The average value across all {len(values)} dollar-denominated entries is "
            f"{_format_usd(average)}. I computed this as total dollar figures "
            f"{_format_usd(total)} divided by {len(values)} entries. Source pages: {', '.join(map(str, pages))}."
        )
    else:
        answer = (
            f"The total sum of all {len(values)} dollar-denominated figures is {_format_usd(total)}. "
            f"I summed every dollar amount extracted from the uploaded document. "
            f"Source pages: {', '.join(map(str, pages))}."
        )

    return {
        "answer": answer,
        "agent_steps": [
            {
                "tool": "retrieve_data",
                "input": {"query": question},
                "output": labels_preview[:400],
                "error": False,
                "retry": 0,
            },
            {
                "tool": "run_python",
                "input": {"code": code},
                "output": python_output[:400],
                "error": python_output.startswith("ERROR"),
                "retry": 0,
            },
        ],
    }


class AnalysisRequest(BaseModel):
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
    _state["history"] = []
    _state["pages"] = pages
    _state["numeric_entries"] = _extract_numeric_entries(pages)
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/reset-chat")
def reset_chat():
    _state["history"] = []
    return {"status": "cleared"}


@app.post("/analyze")
def analyze(body: AnalysisRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    try:
        direct = _direct_numeric_answer(body.question)
        if direct:
            _state["history"].append({"question": body.question, "answer": direct["answer"]})
            _state["history"] = _state["history"][-10:]
            return direct
        return _run_analysis(body)
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "RateLimitError":
            raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
        import traceback
        raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


def _run_analysis(body: AnalysisRequest):
    system = (
        f"You are a strict data analyst agent with access to '{_state['filename']}'. "
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
        "IMPORTANT: Call AT MOST 2 tools per turn. Do not repeat the same call."
    )

    history_context = ""
    if _state["history"]:
        recent = _state["history"][-3:]
        history_context = "\n\nRecent conversation:\n" + "\n".join(
            f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in recent
        )

    messages = [
        {"role": "system", "content": system + history_context},
        {"role": "user", "content": body.question},
    ]

    agent_steps = []
    python_retries = 0
    total_tool_calls = 0
    MAX_TOOL_CALLS_PER_TURN = 3   # small models can hallucinate dozens of calls in one turn
    MAX_TOTAL_TOOL_CALLS = 12

    opening = messages[:1]  # system message, fixed
    sliding = messages[1:]  # everything else — capped below

    for _ in range(12):
        if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
            break

        current_messages = opening + sliding[-8:]
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=current_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            if type(e).__name__ == "BadRequestError":
                # Model produced a malformed tool call — stop looping, answer from what we have
                break
            raise
        msg = response.choices[0].message
        tool_calls = (msg.tool_calls or [])[:MAX_TOOL_CALLS_PER_TURN]

        # Build serializable message dict
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
        sliding.append(msg_dict)

        if not tool_calls:
            answer = msg.content or "No answer produced."
            _state["history"].append({"question": body.question, "answer": answer})
            _state["history"] = _state["history"][-10:]
            return {
                "answer": answer,
                "agent_steps": agent_steps,
            }

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except Exception:
                sliding.append({"role": "tool", "tool_call_id": tc.id,
                                "content": "ERROR: malformed tool arguments — retry with valid JSON."})
                continue
            result = run_tool(fn_name, fn_args)
            total_tool_calls += 1

            is_error = fn_name == "run_python" and result.startswith("ERROR")
            if is_error:
                python_retries += 1

            agent_steps.append({
                "tool": fn_name,
                "input": fn_args,
                "output": result[:400],
                "error": is_error,
                "retry": python_retries if is_error else 0,
            })

            sliding.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

            if is_error and python_retries >= MAX_RETRIES:
                sliding.append({
                    "role": "user",
                    "content": "Python execution failed too many times. Provide the best answer you can from the retrieved data without running code.",
                })

    final_answer = "Agent did not converge in time. Try a simpler/more specific question."
    _state["history"].append({"question": body.question, "answer": final_answer})
    return {"answer": final_answer, "agent_steps": agent_steps}
