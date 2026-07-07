"""App 4 – PDF Report Summarizer Agent  [AGENTIC]
Agent uses tool calls to decide what to retrieve (retrieve_content) and what
sections to write (write_section), one section at a time, grounded in its own
retrieval rather than a single upfront completion.
"""
import os, sys, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import BadRequestError, Groq
from pydantic import BaseModel

from shared.errors import raise_for_groq_error
from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, retrieve

app = FastAPI(title="App 4 – Report Summarizer Agent")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

_state: dict = {"chunks": [], "filename": "", "report": {}, "chat_history": []}


class ChatRequest(BaseModel):
    question: str

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_content",
            "description": (
                "Search the PDF document for content relevant to a specific topic or report section. "
                "Call this multiple times with different queries to gather all needed information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic or question to search for in the document",
                    },
                    "section": {
                        "type": "string",
                        "description": "Which report section this retrieval is for (e.g. 'Executive Summary')",
                    },
                },
                "required": ["query", "section"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_section",
            "description": (
                "Write a completed section of the report. Call this after retrieving enough content "
                "for that section. Each section should be called exactly once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Section title (e.g. 'Executive Summary')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The written section content, grounded in retrieved evidence. Include page citations.",
                    },
                    "pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Page numbers cited in this section",
                    },
                },
                "required": ["title", "content", "pages"],
            },
        },
    },
]


def run_tool(name: str, args: dict, report_sections: dict) -> str:
    if name == "retrieve_content":
        query = str(args.get("query", ""))[:300]
        if not query:
            return "ERROR: missing 'query' argument."
        results = retrieve(query, _state["chunks"], top_k=2)
        if not results:
            return "No relevant content found."
        # Truncate to stay within token limits
        return build_context(results)[:600]

    if name == "write_section":
        if not args.get("title") or not args.get("content"):
            return "ERROR: write_section requires 'title' and 'content'."
        key = str(args["title"]).lower().replace(" ", "_")
        report_sections[key] = {
            "label": args["title"],
            "content": args["content"],
            "pages": args.get("pages", []),
        }
        return "OK"

    return "Unknown tool."


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
    _state["report"] = {}
    _state["chat_history"] = []
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/generate-report")
def generate_report():
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    try:
        return _run_agent()
    except Exception as e:
        raise_for_groq_error(e)


REPORT_SECTIONS = [
    ("executive_summary", "Executive Summary", "overview summary performance results"),
    ("key_themes", "Key Themes", "themes priorities strategy operations"),
    ("data_statistics", "Data & Statistics", "revenue profit growth percentage metrics data statistics"),
    ("recommendations", "Recommendations", "recommendations next steps action plan improvements"),
    ("risks_challenges", "Risks & Challenges", "risks challenges issues constraints threats"),
]


def _build_report_evidence() -> str:
    blocks = []
    for _, title, query in REPORT_SECTIONS:
        results = retrieve(query, _state["chunks"], top_k=2)
        context = build_context(results)[:900] if results else "No relevant content found."
        blocks.append(f"[SECTION: {title}]\n{context}")
    return "\n\n---\n\n".join(blocks)


def _parse_report_json(content: str) -> dict:
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1:
        return {}
    try:
        return json.loads(content[start:end])
    except Exception:
        return {}


AGENT_SYSTEM_PROMPT_TEMPLATE = (
    "You are a report writing agent working on the document '{filename}'.\n"
    "You have two tools: retrieve_content(query, section) to search the PDF for evidence, "
    "and write_section(title, content, pages) to submit a completed section.\n"
    "Produce exactly five sections, in this order: Executive Summary, Key Themes, "
    "Data & Statistics, Recommendations, Risks & Challenges.\n"
    "For each section: call retrieve_content at least once to gather evidence for it, then call "
    "write_section exactly once with content grounded ONLY in retrieved evidence and page citations.\n"
    "Do not invent facts that aren't in the retrieved evidence — if evidence is limited, summarize "
    "what's present instead.\n"
    "Call write_section for all five sections before you finish."
)

MAX_TOOL_CALLS_PER_TURN = 3
MAX_TOTAL_TOOL_CALLS = 20  # 5 sections x (>=1 retrieve + 1 write), with slack


def _run_agent():
    messages = [{"role": "user", "content": AGENT_SYSTEM_PROMPT_TEMPLATE.format(filename=_state["filename"])}]
    report_sections: dict = {}
    steps = []
    total_tool_calls = 0

    for _ in range(15):
        if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
            break
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except BadRequestError:
            break
        msg = response.choices[0].message
        tool_calls = (msg.tool_calls or [])[:MAX_TOOL_CALLS_PER_TURN]

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
            break

        for tc in tool_calls:
            try:
                fn_args = json.loads(tc.function.arguments)
            except Exception:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                  "content": "ERROR: malformed tool arguments — retry with valid JSON."})
                continue
            result = run_tool(tc.function.name, fn_args, report_sections)
            total_tool_calls += 1
            steps.append({"tool": tc.function.name, "section": fn_args.get("section", fn_args.get("title", ""))})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if len(report_sections) >= len(REPORT_SECTIONS):
            break

    if not report_sections:
        # The model never engaged with the tools (or hit BadRequestError immediately) —
        # fall back to a single grounded completion over upfront-retrieved evidence
        # rather than showing nothing.
        evidence = _build_report_evidence()
        fallback_prompt = (
            f"You are a report writing agent. Document: '{_state['filename']}'.\n"
            "Write a grounded report using ONLY the retrieved PDF evidence below.\n"
            "Create exactly five sections: Executive Summary, Key Themes, Data & Statistics, Recommendations, Risks & Challenges.\n"
            "Each section must cite page numbers from its evidence in the pages array and in the content text.\n"
            "If evidence is limited, summarize what is present instead of inventing missing facts.\n\n"
            f"RETRIEVED EVIDENCE BY SECTION:\n{evidence}\n\n"
            "Return ONLY raw JSON in this exact shape:\n"
            '{"report":{"executive_summary":{"label":"Executive Summary","content":"...","pages":[1]},'
            '"key_themes":{"label":"Key Themes","content":"...","pages":[1]},'
            '"data_statistics":{"label":"Data & Statistics","content":"...","pages":[1]},'
            '"recommendations":{"label":"Recommendations","content":"...","pages":[1]},'
            '"risks_challenges":{"label":"Risks & Challenges","content":"...","pages":[1]}}}'
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": fallback_prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = _parse_report_json(response.choices[0].message.content or "")
        report_sections = parsed.get("report", {}) if isinstance(parsed, dict) else {}
        for section in report_sections.values():
            steps.append({"tool": "write_section", "section": section.get("label", "")})

    if not report_sections:
        raise HTTPException(502, "The AI did not return a valid report. Please retry; no fake report was shown.")

    _state["report"] = report_sections
    return {"report": report_sections, "filename": _state["filename"], "steps": steps}


@app.post("/chat")
def chat(body: ChatRequest):
    if not _state["chunks"]:
        raise HTTPException(400, "No PDF uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    results = retrieve(body.question, _state["chunks"], top_k=3)
    context = build_context(results)[:1000] if results else "No relevant content found."

    report_summary = ""
    if _state["report"]:
        report_summary = "\n".join(
            f"- {sec['label']}: {sec['content'][:150]}" for sec in _state["report"].values()
        )[:800]

    history_text = "\n".join(
        f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in _state["chat_history"][-3:]
    )

    prompt = (
        f"You are answering questions about the document '{_state['filename']}'.\n\n"
        f"GENERATED REPORT (for context):\n{report_summary}\n\n"
        f"RETRIEVED DOCUMENT EXCERPTS:\n{context}\n\n"
        + (f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else "")
        + f"NEW QUESTION: {body.question}\n\n"
        "Answer using only the report and retrieved excerpts above. If not covered, say so. "
        "Keep it concise (2-4 sentences) and cite page numbers if available."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
    except Exception as e:
        raise_for_groq_error(e)
    answer = response.choices[0].message.content.strip()
    pages = sorted({r.chunk.page for r in results})

    _state["chat_history"].append({"question": body.question, "answer": answer})
    _state["chat_history"] = _state["chat_history"][-10:]

    return {"answer": answer, "pages": pages}
