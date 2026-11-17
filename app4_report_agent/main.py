"""App 4 – PDF Report Summarizer Agent  [AGENTIC]
Agent uses tool calls to decide what to retrieve (retrieve_content) and what
sections to write (write_section), one section at a time, grounded in its own
retrieval rather than a single upfront completion.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from shared.errors import raise_for_groq_error, require_client
from shared.json_repair import extract_json_object
from shared.llm_agent import run_tool_calling_agent
from shared.llm_client import SetKeyRequest, resolve_model, validate_key
from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, is_grounded, retrieve

app = FastAPI(title="App 4 – Report Summarizer Agent")
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


_state: dict = {"chunks": [], "filename": "", "report": {}, "chat_history": []}


class ChatRequest(BaseModel):
    question: str

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MODEL = "openai/gpt-oss-120b"

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


def normalize_section_key(title: str) -> str:
    cleaned = str(title or "").lower().strip()
    cleaned = cleaned.replace("&", "and")
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    slug = "_".join(cleaned.split())
    if "exec" in slug or "summary" in slug:
        return "executive_summary"
    if "theme" in slug or "priorit" in slug:
        return "key_themes"
    if "data" in slug or "stat" in slug or "metric" in slug or "number" in slug or "financial" in slug:
        return "data_statistics"
    if "recommend" in slug or "next_step" in slug or "action" in slug:
        return "recommendations"
    if "risk" in slug or "challenge" in slug or "threat" in slug or "issue" in slug:
        return "risks_challenges"
    return slug


def run_tool(name: str, args: dict, report_sections: dict) -> str:
    if name == "retrieve_content":
        query = str(args.get("query", ""))[:300]
        if not query:
            return "ERROR: missing 'query' argument."
        results = retrieve(query, _state["chunks"], top_k=3)
        if not results:
            return "No relevant content found."
        # Provide rich context for grounded report generation (up to 2500 chars)
        return build_context(results)[:2500]

    if name == "write_section":
        if not args.get("title") or not args.get("content"):
            return "ERROR: write_section requires 'title' and 'content'."
        raw_title = str(args["title"]).strip()
        key = normalize_section_key(raw_title)
        canonical_titles = {s[0]: s[1] for s in REPORT_SECTIONS}
        label = canonical_titles.get(key, raw_title)
        report_sections[key] = {
            "label": label,
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
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}")
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
    require_client(client)
    # Reset chat history and previous report on re-run for clean idempotency
    _state["chat_history"] = []
    _state["report"] = {}
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
        results = retrieve(query, _state["chunks"], top_k=3)
        context = build_context(results)[:2500] if results else "No relevant content found."
        blocks.append(f"[SECTION: {title}]\n{context}")
    return "\n\n---\n\n".join(blocks)


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
    report_sections: dict = {}

    def run_tool_bound(name: str, args: dict) -> str:
        return run_tool(name, args, report_sections)

    initial_messages = [HumanMessage(content=AGENT_SYSTEM_PROMPT_TEMPLATE.format(filename=_state["filename"]))]
    model = resolve_model(provider, MODEL)

    result = run_tool_calling_agent(
        client, model=model, initial_messages=initial_messages, tools=TOOLS, run_tool=run_tool_bound,
        max_iterations=15, max_tool_calls_per_turn=MAX_TOOL_CALLS_PER_TURN, max_total_tool_calls=MAX_TOTAL_TOOL_CALLS,
        stop_when=lambda: len(report_sections) >= len(REPORT_SECTIONS),
    )

    steps = [
        {"tool": s["tool"], "section": s["input"].get("section", s["input"].get("title", ""))}
        for s in result.agent_steps
    ]

    if not report_sections:
        # The model never engaged with the tools (or hit a safety cap immediately) —
        # fall back to a single grounded completion over upfront-retrieved evidence
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
        response = client.bind(model=model, temperature=0, response_format={"type": "json_object"}).invoke(
            [HumanMessage(content=fallback_prompt)]
        )
        parsed = extract_json_object(response.content or "")
        raw_fallback = parsed.get("report", {}) if isinstance(parsed, dict) else {}
        for k, section in raw_fallback.items():
            norm_k = normalize_section_key(section.get("label", k))
            report_sections[norm_k] = section
            steps.append({"tool": "write_section", "section": section.get("label", "")})

    # Guarantee all 5 canonical sections exist and are ordered predictably
    canonical_titles = {s[0]: s[1] for s in REPORT_SECTIONS}
    ordered_report = {}
    for key, title, _ in REPORT_SECTIONS:
        if key in report_sections:
            sec = report_sections[key]
            if not sec.get("label"):
                sec["label"] = title
            ordered_report[key] = sec
        else:
            ordered_report[key] = {
                "label": title,
                "content": "No relevant content found in the document.",
                "pages": [],
            }
    report_sections = ordered_report

    if not any(s.get("content") and s.get("content") != "No relevant content found in the document." for s in report_sections.values()):
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
    if not is_grounded(results) and not _state["report"]:
        return {"answer": "No relevant content found in the document.", "pages": []}
    require_client(client)
    context = build_context(results)[:2500] if results else "No relevant content found."

    report_summary = ""
    if _state["report"]:
        report_summary = "\n\n".join(
            f"### {sec['label']}\n{sec['content']}" for sec in _state["report"].values()
        )[:3000]

    history_text = "\n".join(
        f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in _state["chat_history"][-3:]
    )

    prompt = (
        f"You are answering questions about the document '{_state['filename']}'.\n\n"
        f"GENERATED REPORT:\n{report_summary}\n\n"
        f"RETRIEVED DOCUMENT EXCERPTS:\n{context}\n\n"
        + (f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else "")
        + f"QUESTION: {body.question}\n\n"
        "Instructions:\n"
        "- Answer using ONLY the generated report and retrieved document excerpts above.\n"
        "- If the question asks for information not present in the document or report, explicitly state that it is not covered or not mentioned.\n"
        "- If the question contains a false premise, clearly clarify the true facts from the text.\n"
        "- Keep it concise (2-4 sentences)."
    )

    try:
        response = client.bind(model=resolve_model(provider, "llama-3.1-8b-instant"), temperature=0).invoke(
            [HumanMessage(content=prompt)]
        )
    except Exception as e:
        raise_for_groq_error(e)
    answer = response.content.strip()

    negation_phrases = [
        "not covered",
        "not mentioned",
        "not found",
        "does not mention",
        "no information",
        "not specified",
        "no relevant content",
        "not state",
        "not provide",
        "not discussed",
    ]
    is_negative = any(phrase in answer.lower() for phrase in negation_phrases)

    pages = []
    if is_grounded(results) and not is_negative:
        pages = sorted({r.chunk.page for r in results if r.score >= 0.20})

    _state["chat_history"].append({"question": body.question, "answer": answer})
    _state["chat_history"] = _state["chat_history"][-10:]

    return {"answer": answer, "pages": pages}
