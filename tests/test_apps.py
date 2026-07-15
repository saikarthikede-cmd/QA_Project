"""Smoke tests for each FastAPI app endpoint."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app1_resume_screener import main as app1_main
from app2_doc_diff import main as app2_main
from app3_faq_generator import main as app3_main
from app4_report_agent import main as app4_main
from app5_policy_triage import main as app5_main
from app6_data_analyst import main as app6_main


def FakeResponse(content: str, tool_calls=None) -> AIMessage:
    """Builds a fake LangChain AIMessage — the shape ChatOpenAI actually
    returns from .invoke(). tool_calls, if given, is a list of
    {"name", "args", "id", "type": "tool_call"} dicts (args pre-parsed,
    not a JSON string — LangChain parses tool-call arguments itself)."""
    return AIMessage(content=content, tool_calls=tool_calls or [])


def make_tool_call(name: str, args: dict, call_id: str = "tc_1") -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class FakeLLMClient:
    """LangChain-shaped fake: supports the bind_tools()/bind()/invoke() chain
    the real ChatOpenAI-based code uses. Cycles through scripted responses,
    repeating the last one once exhausted — matches the old single-canned-
    response fake's behavior when only one response is given."""

    def __init__(self, *responses: AIMessage):
        self.responses = list(responses)
        self.i = 0
        self.call_count = 0  # lets tests prove the agent actually looped, not just returned response 0

    def bind_tools(self, tools, tool_choice=None):
        return self

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.call_count += 1
        response = self.responses[self.i]
        if self.i < len(self.responses) - 1:
            self.i += 1
        return response


def set_fake_key(monkeypatch, app_module, client: TestClient, response: AIMessage) -> FakeLLMClient:
    """v2: the LLM client lives in a per-session store, not a module global —
    so tests go through the real /api/set-key flow (with validate_key mocked
    to skip the real provider call) instead of poking `app_module.client`."""
    fake_client = FakeLLMClient(response)
    monkeypatch.setattr(app_module, "validate_key", lambda provider, api_key: (fake_client, provider))
    r = client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"})
    assert r.status_code == 200
    return fake_client


@pytest.fixture
def upload_pdf(text_pdf):
    def _upload(client: TestClient, url: str = "/upload"):
        pdf_bytes = text_pdf(
            "Total revenue was $100. Net profit was $20. Employees: 10. "
            "Return policy: 30 days. Shipping: free over $50."
        )
        response = client.post(url, files={"file": ("test.pdf", pdf_bytes, "application/pdf")})
        assert response.status_code == 200
        return response.json()

    return _upload


def test_app1_upload_and_mock_screen(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app1_main.app)
    jd_bytes = text_pdf(
        "Senior Backend Engineer. Requires Python, FastAPI, PostgreSQL, AWS, 5+ years experience."
    )

    # Upload JD
    r = client.post("/upload-jd", files={"file": ("jd.pdf", jd_bytes, "application/pdf")})
    assert r.status_code == 200

    # Upload resume
    resume_bytes = text_pdf(
        "Sarah Chen. 8 years experience. Python, FastAPI, PostgreSQL, AWS, Kubernetes."
    )
    r = client.post("/upload-resume", files={"file": ("resume.pdf", resume_bytes, "application/pdf")})
    assert r.status_code == 200

    set_fake_key(monkeypatch, app1_main, client, FakeResponse(
        '{"score": 90, "recommendation": "Strong Match", '
        '"matched_skills": ["Python", "FastAPI"], "missing_skills": [], '
        '"red_flags": [], "summary": "Great match.", "cited_pages": [1]}'
    ))
    r = client.post("/screen")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data["results"][0]["score"] == 90


def test_app1_screen_agent_uses_search_tool(text_pdf, upload_pdf, monkeypatch):
    """Proves search_resume_evidence is actually wired up end to end: script
    the model calling the tool, then answering — not just the trivial
    no-tool-call path every other test here exercises."""
    client = TestClient(app1_main.app)
    jd_bytes = text_pdf(
        "Senior Backend Engineer. Requires Python, FastAPI, PostgreSQL, AWS, 5+ years experience."
    )
    r = client.post("/upload-jd", files={"file": ("jd.pdf", jd_bytes, "application/pdf")})
    assert r.status_code == 200
    resume_bytes = text_pdf(
        "Sarah Chen. 8 years experience. Python, FastAPI, PostgreSQL, AWS, Kubernetes."
    )
    r = client.post("/upload-resume", files={"file": ("resume.pdf", resume_bytes, "application/pdf")})
    assert r.status_code == 200

    fake_client = FakeLLMClient(
        FakeResponse("", tool_calls=[make_tool_call("search_resume_evidence", {"query": "AWS certifications"})]),
        FakeResponse(
            '{"score": 85, "recommendation": "Strong Match", "matched_skills": ["Python"], '
            '"missing_skills": [], "red_flags": [], "summary": "Good fit.", "cited_pages": [1]}'
        ),
    )
    monkeypatch.setattr(app1_main, "validate_key", lambda provider, api_key: (fake_client, provider))
    assert client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"}).status_code == 200

    r = client.post("/screen")
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["score"] == 85
    assert fake_client.call_count == 2, "one call for the tool call, one for the final answer"


def test_app1_rejects_non_pdf():
    client = TestClient(app1_main.app)
    r = client.post("/upload-jd", files={"file": ("bad.txt", b"not a pdf", "text/plain")})
    assert r.status_code == 400


def test_app2_upload_and_mock_analyze(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app2_main.app)
    doc_a = text_pdf("Return policy: 30 days. Shipping: 5-7 days.")
    doc_b = text_pdf("Return policy: 60 days. Shipping: 3-5 days.")

    r = client.post("/upload-a", files={"file": ("a.pdf", doc_a, "application/pdf")})
    assert r.status_code == 200
    r = client.post("/upload-b", files={"file": ("b.pdf", doc_b, "application/pdf")})
    assert r.status_code == 200

    set_fake_key(monkeypatch, app2_main, client, FakeResponse(
        '{"summary": "Policies updated.", "severity": "Major", "change_count": 2, '
        '"added": [], "removed": [], "modified": [], "unchanged_note": ""}'
    ))
    r = client.post("/analyze")
    assert r.status_code == 200
    assert "summary" in r.json()


def test_app2_analyze_agent_uses_search_tool(text_pdf, upload_pdf, monkeypatch):
    """Proves search_document is actually wired up: script the model calling
    it on Document A, then finalizing the comparison."""
    client = TestClient(app2_main.app)
    doc_a = text_pdf("Return policy: 30 days. Shipping: 5-7 days.")
    doc_b = text_pdf("Return policy: 60 days. Shipping: 3-5 days.")
    r = client.post("/upload-a", files={"file": ("a.pdf", doc_a, "application/pdf")})
    assert r.status_code == 200
    r = client.post("/upload-b", files={"file": ("b.pdf", doc_b, "application/pdf")})
    assert r.status_code == 200

    fake_client = FakeLLMClient(
        FakeResponse("", tool_calls=[make_tool_call("search_document", {"doc": "A", "query": "shipping"})]),
        FakeResponse(
            '{"summary": "Policies updated.", "severity": "Major", "change_count": 2, '
            '"added": [], "removed": [], "modified": [], "unchanged_note": ""}'
        ),
    )
    monkeypatch.setattr(app2_main, "validate_key", lambda provider, api_key: (fake_client, provider))
    assert client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"}).status_code == 200

    r = client.post("/analyze")
    assert r.status_code == 200
    assert "summary" in r.json()
    assert fake_client.call_count == 2, "one call for the tool call, one for the final answer"


def test_app3_upload_and_mock_generate(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app3_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app3_main, client, FakeResponse(
        '{"faqs": [{"question": "What is the return policy?", "answer": "30 days.", "page": 1}]}'
    ))
    r = client.post("/generate")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1


def test_app3_generate_agent_uses_search_tool(text_pdf, upload_pdf, monkeypatch):
    """Proves search_document is actually wired up for FAQ generation too."""
    client = TestClient(app3_main.app)
    upload_pdf(client, "/upload")

    fake_client = FakeLLMClient(
        FakeResponse("", tool_calls=[make_tool_call("search_document", {"query": "shipping policy"})]),
        FakeResponse('{"faqs": [{"question": "What is the return policy?", "answer": "30 days.", "page": 1}]}'),
    )
    monkeypatch.setattr(app3_main, "validate_key", lambda provider, api_key: (fake_client, provider))
    assert client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"}).status_code == 200

    r = client.post("/generate")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1
    assert fake_client.call_count == 2, "one call for the tool call, one for the final answer"


def test_app3_faq_crud(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app3_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app3_main, client, FakeResponse(
        '{"faqs": [{"question": "Q1", "answer": "A1", "page": 1}, '
        '{"question": "Q2", "answer": "A2", "page": 1}]}'
    ))
    client.post("/generate")

    # Delete first FAQ
    r = client.delete("/faqs/0")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # Get list
    r = client.get("/faqs")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1


def test_app4_upload_and_mock_report(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app4_main, client, FakeResponse(
        "",
        tool_calls=[make_tool_call(
            "write_section",
            {"title": "Executive Summary", "content": "Revenue grew.", "pages": [1]},
        )],
    ))
    r = client.post("/generate-report")
    assert r.status_code == 200
    data = r.json()
    assert "executive_summary" in data["report"]
    assert any(step["tool"] == "write_section" for step in data["steps"])


def test_app5_upload_and_mock_triage(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse(
        '{"decision": "AUTO-RESOLVE", "reason": "Within policy.", '
        '"draft_reply": "Approved.", "policy_pages": [1]}'
    ))
    r = client.post("/triage", json={"ticket": "I want a refund within 7 days."})
    assert r.status_code == 200
    assert r.json()["decision"] == "AUTO-RESOLVE"


def test_app5_ask_followup(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse("The return policy allows 30 days."))
    r = client.post("/ask", json={"question": "What is the return policy?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "The return policy allows 30 days."
    assert "pages" in data


def test_app5_ask_before_upload_rejected():
    client = TestClient(app5_main.app)
    app5_main._state["chunks"] = []  # _state is a module global — reset in case an earlier test left it populated
    r = client.post("/ask", json={"question": "What is the return policy?"})
    assert r.status_code == 400


def test_app6_upload_and_mock_analysis(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app6_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app6_main, client, FakeResponse(
        "",
        tool_calls=[make_tool_call("run_python", {"code": "print(100 - 20)"})],
    ))
    r = client.post("/analyze", json={"question": "What is revenue minus profit?"})
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert any(step["tool"] == "run_python" for step in data["agent_steps"])


def test_app6_analyze_never_converges_returns_honest_fallback(text_pdf, upload_pdf, monkeypatch):
    """Reproduces the QA-reported failure mode ("Agent did not converge in
    time") directly: the model keeps calling tools and never gives a final
    answer. Must stop at the safety cap and return the honest fallback
    message, not hang or crash."""
    client = TestClient(app6_main.app)
    upload_pdf(client, "/upload")

    # Single scripted response repeats forever (FakeLLMClient behavior) —
    # every turn is another tool call, the model never stops to answer.
    set_fake_key(monkeypatch, app6_main, client, FakeResponse(
        "", tool_calls=[make_tool_call("retrieve_data", {"query": "all figures"})],
    ))
    r = client.post("/analyze", json={"question": "What is the total sum of all figures?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "Agent did not converge in time. Try a simpler/more specific question."
    assert len(data["agent_steps"]) == 12  # stopped exactly at max_total_tool_calls, not runaway


def test_app6_sandbox_rejects_malicious_code(text_pdf, upload_pdf, monkeypatch):
    client = TestClient(app6_main.app)
    upload_pdf(client, "/upload")

    set_fake_key(monkeypatch, app6_main, client, FakeResponse(
        "",
        tool_calls=[make_tool_call("run_python", {"code": "import os\nprint(os.getcwd())"})],
    ))
    r = client.post("/analyze", json={"question": "Try to break out."})
    assert r.status_code == 200
    data = r.json()
    python_step = next(s for s in data["agent_steps"] if s["tool"] == "run_python")
    assert python_step["error"] is True
