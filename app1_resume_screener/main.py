"""App 1 – Resume Screener  [RAG]
Embeds both JD and resumes as chunks.
Retrieves evidence from each resume using JD-derived queries, then scores.
Every assessment is grounded in retrieved chunks with page citations.
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
from typing import List

from shared.pdf_utils import build_context, chunk_pages, embed_chunks, extract_pages, retrieve

app = FastAPI(title="App 1 – Resume Screener (RAG)")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

_state: dict = {
    "jd_chunks": [],
    "jd_filename": "",
    "resumes": {},  # filename -> List[Chunk]
    "last_results": [],  # last screening results for chat context
    "chat_history": [],
}


class AskRequest(BaseModel):
    question: str

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Fixed JD-screening queries used to retrieve evidence from each resume
SCREEN_QUERIES = [
    "years of professional experience",
    "programming languages frameworks libraries",
    "cloud infrastructure DevOps deployment",
    "databases storage systems",
    "team leadership management mentoring",
    "education degree certifications",
    "domain industry specific experience",
    "architecture design system design",
    "testing CI CD quality engineering",
    "communication collaboration cross-functional",
]


def _parse_json(content: str) -> dict | list:
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    s = content.find("{") if "{" in content else content.find("[")
    e = content.rfind("}") + 1 if "{" in content else content.rfind("]") + 1
    if s == -1:
        return {}
    raw = content[s:e]
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Repair common model mistakes: trailing commas before } or ]
    try:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
    except Exception:
        return {}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/upload-jd")
async def upload_jd(file: UploadFile = File(...)):
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
    _state["jd_chunks"] = chunks
    _state["jd_filename"] = file.filename
    _state["resumes"] = {}
    _state["last_results"] = []
    _state["chat_history"] = []
    return {"status": "ok", "filename": file.filename, "chunks": len(chunks)}


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    if not _state["jd_chunks"]:
        raise HTTPException(400, "Upload the Job Description first.")
    if file.filename in _state["resumes"]:
        raise HTTPException(400, f"'{file.filename}' is already loaded.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large ({len(pdf_bytes)/1024/1024:.1f} MB). Max 50 MB.")
    try:
        pages = extract_pages(pdf_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    chunks = chunk_pages(pages, source=file.filename)
    chunks = embed_chunks(chunks)
    _state["resumes"][file.filename] = chunks
    return {"status": "ok", "filename": file.filename, "total_resumes": len(_state["resumes"])}


@app.delete("/resumes/{filename}")
def remove_resume(filename: str):
    if filename not in _state["resumes"]:
        raise HTTPException(404, "Resume not found.")
    del _state["resumes"][filename]
    return {"status": "removed", "remaining": len(_state["resumes"])}


@app.post("/screen")
def screen():
    if not _state["jd_chunks"]:
        raise HTTPException(400, "No Job Description uploaded.")
    if not _state["resumes"]:
        raise HTTPException(400, "No resumes uploaded.")
    try:
        return _run_screen()
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "RateLimitError":
            raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
        import traceback
        raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


def _run_screen():
    # Build JD context once (retrieve broad overview of the JD)
    jd_overview = retrieve("job requirements responsibilities qualifications", _state["jd_chunks"], top_k=3)
    jd_context = build_context(jd_overview)[:600]

    results = []
    for filename, resume_chunks in _state["resumes"].items():
        # RAG: retrieve evidence from this resume using each screening query
        seen_texts = set()
        evidence: List = []
        for query in SCREEN_QUERIES:
            for r in retrieve(query, resume_chunks, top_k=2):
                if r.chunk.text not in seen_texts:
                    evidence.append(r)
                    seen_texts.add(r.chunk.text)

        resume_context = build_context(evidence[:8])[:800]
        cited_pages = sorted({r.chunk.page for r in evidence})

        # Semantic similarity score — pure embedding cosine similarity, independent of the LLM.
        # Lets QA compare/contrast embedding-based matching vs LLM judgment.
        semantic_score = round(sum(r.score for r in evidence) / len(evidence) * 100, 1) if evidence else 0.0

        prompt = (
            "You are a strict recruiting assistant. Score this candidate ONLY based on the retrieved "
            "resume evidence provided below. Do NOT invent or assume skills not present in the evidence.\n\n"
            f"JOB DESCRIPTION CONTEXT (from {_state['jd_filename']}):\n{jd_context}\n\n"
            f"RETRIEVED RESUME EVIDENCE (from {filename}, pages {cited_pages}):\n{resume_context}\n\n"
            "Based ONLY on the above evidence, return a JSON object with exactly:\n"
            "- score: integer 0-100\n"
            "- recommendation: 'Strong Match', 'Possible Match', or 'Not Suitable'\n"
            "- matched_skills: list of strings (skills found in the resume evidence that match the JD)\n"
            "- missing_skills: list of strings (JD requirements not found in any retrieved chunk)\n"
            "- red_flags: list of strings (concerns from the evidence — empty list if none)\n"
            "- summary: 2-3 sentence evaluation citing specific pages\n"
            "- cited_pages: list of page integers where evidence was found\n\n"
            "Score guide: 80-100=Strong Match, 50-79=Possible Match, 0-49=Not Suitable.\n"
            "Return ONLY raw JSON."
        )

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = _parse_json(response.choices[0].message.content.strip())
        if not data or "score" not in data:
            # Retry once without forced JSON mode before giving up
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            data = _parse_json(response.choices[0].message.content.strip())
        if not data or "score" not in data:
            # Honest failure — never silently score a real candidate as 0
            data = {
                "score": None, "recommendation": "Screening Failed",
                "matched_skills": [], "missing_skills": [],
                "red_flags": ["AI response could not be parsed — re-run screening"],
                "summary": "The AI returned an unparseable evaluation for this candidate. "
                           "Click Screen Candidates again to retry.",
                "cited_pages": cited_pages,
            }
        # Normalize types so the frontend never crashes
        for key in ("matched_skills", "missing_skills", "red_flags", "cited_pages"):
            if not isinstance(data.get(key), list):
                data[key] = []
        if data.get("score") is not None and not isinstance(data.get("score"), int):
            try:
                data["score"] = int(float(data["score"]))
            except Exception:
                data["score"] = 0
        data["candidate"] = filename
        data["semantic_score"] = semantic_score
        results.append(data)

    results.sort(key=lambda x: x.get("score") or 0, reverse=True)
    _state["last_results"] = results
    _state["chat_history"] = []
    return {"results": results, "jd": _state["jd_filename"]}


@app.post("/ask")
def ask(body: AskRequest):
    if not _state["jd_chunks"]:
        raise HTTPException(400, "No Job Description uploaded yet.")
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    # RAG: retrieve from all resumes + JD simultaneously
    all_chunks = _state["jd_chunks"]
    for resume_chunks in _state["resumes"].values():
        all_chunks = all_chunks + resume_chunks

    results = retrieve(body.question, all_chunks, top_k=4)
    context = build_context(results)[:1200] if results else "No relevant content found."

    # Summarise screening results so agent can reference scores/skills
    screening_summary = ""
    if _state["last_results"]:
        lines = []
        for r in _state["last_results"]:
            lines.append(
                f"- {r['candidate']}: AI Score {r.get('score',0)}/100, "
                f"Semantic {r.get('semantic_score',0)}%, "
                f"Recommendation: {r.get('recommendation','')}, "
                f"Matched: {', '.join(r.get('matched_skills',[])[:5])}, "
                f"Missing: {', '.join(r.get('missing_skills',[])[:5])}"
            )
        screening_summary = "\n".join(lines)

    history_text = "\n".join(
        f"Q: {h['question']}\nA: {h['answer'][:200]}" for h in _state["chat_history"][-3:]
    )

    prompt = (
        f"You are answering questions about a recruitment screening for '{_state['jd_filename']}'.\n\n"
        + (f"SCREENING RESULTS SUMMARY:\n{screening_summary}\n\n" if screening_summary else "")
        + f"RETRIEVED DOCUMENT EXCERPTS (JD + resumes):\n{context}\n\n"
        + (f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else "")
        + f"QUESTION: {body.question}\n\n"
        "Answer using only the screening results and retrieved excerpts above. "
        "Be specific — name candidates, cite scores, quote evidence. "
        "Keep the answer concise (3-5 sentences) and cite page numbers where relevant."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
    except Exception as e:
        if type(e).__name__ == "RateLimitError":
            raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
        import traceback
        raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    answer = response.choices[0].message.content.strip()
    pages = sorted({r.chunk.page for r in results})

    _state["chat_history"].append({"question": body.question, "answer": answer})
    _state["chat_history"] = _state["chat_history"][-10:]

    return {"answer": answer, "pages": pages}

