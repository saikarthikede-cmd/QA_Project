"""Comprehensive regression and edge-case tests for App 4 – Report Summarizer Agent."""
from __future__ import annotations

import io
from pathlib import Path
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest
from pypdf import PdfWriter

from app4_report_agent import main as app4_main


def _create_fast_pdf(text: str) -> bytes:
    """Create a minimal valid text PDF using pypdf without scanning Windows system fonts."""
    # We can create a valid PDF using pypdf directly
    from tests.conftest import make_text_pdf
    return make_text_pdf(text)


def FakeResponse(content: str, tool_calls=None) -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def make_tool_call(name: str, args: dict, call_id: str = "tc_1") -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class FakeLLMClient:
    def __init__(self, *responses: AIMessage):
        self.responses = list(responses)
        self.i = 0
        self.call_count = 0

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
    fake_client = FakeLLMClient(response)
    monkeypatch.setattr(app_module, "validate_key", lambda provider, api_key: (fake_client, provider))
    r = client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"})
    assert r.status_code == 200
    return fake_client


@pytest.fixture
def sample_pdf_bytes():
    pdf_path = Path("test_pdfs/app4_nexora_annual_report.pdf")
    if pdf_path.exists():
        return pdf_path.read_bytes()
    return _create_fast_pdf(
        "Nexora Financial Services - Annual Report 2023\n"
        "Total revenue reached $142 million, a 23% increase year-over-year. Net profit grew to $31.2 million.\n"
        "Recommendations: Accelerate NexoraPay international rollout.\n"
        "Risks: Regulatory compliance costs increased 18%."
    )


@pytest.fixture
def upload_report_pdf(sample_pdf_bytes):
    def _upload(client: TestClient, endpoint: str = "/upload"):
        return client.post(endpoint, files={"file": ("report.pdf", sample_pdf_bytes, "application/pdf")})
    return _upload


def test_app4_normalize_section_key():
    assert app4_main.normalize_section_key("Executive Summary") == "executive_summary"
    assert app4_main.normalize_section_key("Key Themes") == "key_themes"
    assert app4_main.normalize_section_key("Key Themes and Priorities") == "key_themes"
    assert app4_main.normalize_section_key("Data & Statistics") == "data_statistics"
    assert app4_main.normalize_section_key("Data and Statistics") == "data_statistics"
    assert app4_main.normalize_section_key("Recommendations") == "recommendations"
    assert app4_main.normalize_section_key("Action Plan & Recommendations") == "recommendations"
    assert app4_main.normalize_section_key("Risks & Challenges") == "risks_challenges"
    assert app4_main.normalize_section_key("Risks and Challenges") == "risks_challenges"


def test_app4_upload_rejects_non_pdf():
    client = TestClient(app4_main.app)
    r = client.post("/upload", files={"file": ("bad.txt", b"plain text content", "text/plain")})
    assert r.status_code == 400
    assert "Only PDF files" in r.json()["detail"]


def test_app4_upload_rejects_corrupted_pdf():
    client = TestClient(app4_main.app)
    r = client.post("/upload", files={"file": ("bad.pdf", b"garbage corrupt bytes", "application/pdf")})
    assert r.status_code in (400, 422)


def test_app4_generate_report_before_upload_fails():
    client = TestClient(app4_main.app)
    app4_main._state["chunks"] = []
    r = client.post("/generate-report")
    assert r.status_code == 400
    assert "No PDF uploaded" in r.json()["detail"]


def test_app4_chat_before_upload_fails():
    client = TestClient(app4_main.app)
    app4_main._state["chunks"] = []
    r = client.post("/chat", json={"question": "What is the revenue?"})
    assert r.status_code == 400
    assert "No PDF uploaded" in r.json()["detail"]


def test_app4_chat_empty_question_fails(upload_report_pdf):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)
    r = client.post("/chat", json={"question": "   "})
    assert r.status_code == 400
    assert "cannot be empty" in r.json()["detail"]


def test_app4_generate_report_agent_flow_and_guarantees_all_5_sections(upload_report_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)

    fake_client = FakeLLMClient(
        FakeResponse("", tool_calls=[make_tool_call("retrieve_content", {"query": "revenue results", "section": "Executive Summary"})]),
        FakeResponse("", tool_calls=[make_tool_call("write_section", {"title": "Executive Summary", "content": "Total revenue was $142M.", "pages": [1]})]),
        FakeResponse("", tool_calls=[make_tool_call("write_section", {"title": "Data & Statistics", "content": "Net profit reached $31.2M.", "pages": [1]})]),
        FakeResponse("Finished all available sections."),
    )
    monkeypatch.setattr(app4_main, "validate_key", lambda provider, api_key: (fake_client, provider))
    client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"})

    r = client.post("/generate-report")
    assert r.status_code == 200
    data = r.json()
    report = data["report"]

    expected_keys = ["executive_summary", "key_themes", "data_statistics", "recommendations", "risks_challenges"]
    for k in expected_keys:
        assert k in report
        assert "label" in report[k]
        assert "content" in report[k]
        assert "pages" in report[k]

    assert "Total revenue" in report["executive_summary"]["content"]
    assert "$31.2M" in report["data_statistics"]["content"]

    # Missing sections say so explicitly with empty pages
    assert "No relevant content found" in report["key_themes"]["content"]
    assert report["key_themes"]["pages"] == []

    assert any(s["tool"] == "retrieve_content" for s in data["steps"])
    assert any(s["tool"] == "write_section" for s in data["steps"])


def test_app4_generate_report_fallback_when_no_tools_called(upload_report_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)

    fallback_json = (
        '{"report": {'
        '"executive_summary": {"label": "Executive Summary", "content": "Revenue grew.", "pages": [1]},'
        '"key_themes": {"label": "Key Themes", "content": "Digital growth.", "pages": [1]},'
        '"data_statistics": {"label": "Data & Statistics", "content": "Margin 22%.", "pages": [1]},'
        '"recommendations": {"label": "Recommendations", "content": "Expand app.", "pages": [1]},'
        '"risks_challenges": {"label": "Risks & Challenges", "content": "Compliance costs.", "pages": [1]}'
        '}}'
    )
    fake_client = FakeLLMClient(FakeResponse(fallback_json))
    monkeypatch.setattr(app4_main, "validate_key", lambda provider, api_key: (fake_client, provider))
    client.post("/api/set-key", json={"provider": "groq", "api_key": "test-key"})

    r = client.post("/generate-report")
    assert r.status_code == 200
    data = r.json()
    assert len(data["report"]) == 5
    assert data["report"]["executive_summary"]["content"] == "Revenue grew."


def test_app4_chat_grounded_answer(upload_report_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)

    set_fake_key(monkeypatch, app4_main, client, FakeResponse("Total revenue in 2023 was $142 million, up 23% YoY."))

    r = client.post("/chat", json={"question": "What was total revenue in 2023?"})
    assert r.status_code == 200
    data = r.json()
    assert "142 million" in data["answer"]
    assert len(data["pages"]) > 0


def test_app4_chat_out_of_scope_returns_empty_pages(upload_report_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)

    set_fake_key(monkeypatch, app4_main, client, FakeResponse("The CEO of Nexora is not mentioned in the document."))

    r = client.post("/chat", json={"question": "Who is the CEO of Nexora?"})
    assert r.status_code == 200
    data = r.json()
    assert "not mentioned" in data["answer"].lower()
    # Critical QA requirement: out of scope / negative answers must NOT falsely cite pages
    assert data["pages"] == []


def test_app4_rerun_resets_chat_history(upload_report_pdf, monkeypatch):
    client = TestClient(app4_main.app)
    upload_report_pdf(client)

    set_fake_key(
        monkeypatch,
        app4_main,
        client,
        FakeResponse("", tool_calls=[make_tool_call("write_section", {"title": "Executive Summary", "content": "Summary 1.", "pages": [1]})]),
    )
    client.post("/generate-report")

    set_fake_key(monkeypatch, app4_main, client, FakeResponse("Follow-up answer."))
    client.post("/chat", json={"question": "What is the revenue?"})
    assert len(app4_main._state["chat_history"]) == 1

    set_fake_key(
        monkeypatch,
        app4_main,
        client,
        FakeResponse("", tool_calls=[make_tool_call("write_section", {"title": "Executive Summary", "content": "Summary 2.", "pages": [1]})]),
    )
    r = client.post("/generate-report")
    assert r.status_code == 200
    assert len(app4_main._state["chat_history"]) == 0
