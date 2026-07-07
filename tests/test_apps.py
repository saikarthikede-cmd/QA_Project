"""Smoke tests for each FastAPI app endpoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Ensure a key is present so the apps can be imported; tests mock the client anyway.
if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "dummy-for-tests"

from app1_resume_screener import main as app1_main
from app2_doc_diff import main as app2_main
from app3_faq_generator import main as app3_main
from app4_report_agent import main as app4_main
from app5_policy_triage import main as app5_main
from app6_data_analyst import main as app6_main


class FakeMessage:
    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, content: str, tool_calls=None):
        self.message = FakeMessage(content, tool_calls)


class FakeResponse:
    def __init__(self, content: str, tool_calls=None):
        self.choices = [FakeChoice(content, tool_calls)]


class FakeCompletions:
    def __init__(self, response: FakeResponse):
        self._response = response

    def create(self, *args, **kwargs):
        return self._response


class FakeChat:
    def __init__(self, completions: FakeCompletions):
        self.completions = completions


class FakeGroqClient:
    def __init__(self, response: FakeResponse):
        self.chat = FakeChat(FakeCompletions(response))


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


def test_app1_upload_and_mock_screen(text_pdf, upload_pdf):
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

    # Mock the Groq client for /screen
    app1_main.client = FakeGroqClient(
        FakeResponse(
            '{"score": 90, "recommendation": "Strong Match", '
            '"matched_skills": ["Python", "FastAPI"], "missing_skills": [], '
            '"red_flags": [], "summary": "Great match.", "cited_pages": [1]}'
        )
    )
    r = client.post("/screen")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data["results"][0]["score"] == 90


def test_app1_rejects_non_pdf():
    client = TestClient(app1_main.app)
    r = client.post("/upload-jd", files={"file": ("bad.txt", b"not a pdf", "text/plain")})
    assert r.status_code == 400


def test_app2_upload_and_mock_analyze(text_pdf, upload_pdf):
    client = TestClient(app2_main.app)
    doc_a = text_pdf("Return policy: 30 days. Shipping: 5-7 days.")
    doc_b = text_pdf("Return policy: 60 days. Shipping: 3-5 days.")

    r = client.post("/upload-a", files={"file": ("a.pdf", doc_a, "application/pdf")})
    assert r.status_code == 200
    r = client.post("/upload-b", files={"file": ("b.pdf", doc_b, "application/pdf")})
    assert r.status_code == 200

    app2_main.client = FakeGroqClient(
        FakeResponse(
            '{"summary": "Policies updated.", "severity": "Major", "change_count": 2, '
            '"added": [], "removed": [], "modified": [], "unchanged_note": ""}'
        )
    )
    r = client.post("/analyze")
    assert r.status_code == 200
    assert "summary" in r.json()


def test_app3_upload_and_mock_generate(text_pdf, upload_pdf):
    client = TestClient(app3_main.app)
    upload_pdf(client, "/upload")

    app3_main.client = FakeGroqClient(
        FakeResponse(
            '[{"question": "What is the return policy?", "answer": "30 days.", "page": 1}]'
        )
    )
    r = client.post("/generate")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1


def test_app3_faq_crud(text_pdf, upload_pdf):
    client = TestClient(app3_main.app)
    upload_pdf(client, "/upload")

    app3_main.client = FakeGroqClient(
        FakeResponse(
            '[{"question": "Q1", "answer": "A1", "page": 1}, '
            '{"question": "Q2", "answer": "A2", "page": 1}]'
        )
    )
    client.post("/generate")

    # Delete first FAQ
    r = client.delete("/faqs/0")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # Get list
    r = client.get("/faqs")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1


def test_app4_upload_and_mock_report(text_pdf, upload_pdf):
    client = TestClient(app4_main.app)
    upload_pdf(client, "/upload")

    app4_main.client = FakeGroqClient(
        FakeResponse(
            "",
            tool_calls=[
                type(
                    "ToolCall",
                    (),
                    {
                        "id": "tc_1",
                        "function": type(
                            "Function",
                            (),
                            {
                                "name": "write_section",
                                "arguments": '{"title": "Executive Summary", "content": "Revenue grew.", "pages": [1]}',
                            },
                        )(),
                    },
                )()
            ],
        )
    )
    # SSE endpoint returns event-stream; just verify it streams without errors.
    with client.stream("GET", "/generate-report") as response:
        assert response.status_code == 200
        chunks = [chunk for chunk in response.iter_text()]
        assert any("done" in c for c in chunks)


def test_app5_upload_and_mock_triage(text_pdf, upload_pdf):
    client = TestClient(app5_main.app)
    upload_pdf(client, "/upload")

    app5_main.client = FakeGroqClient(
        FakeResponse(
            '{"decision": "AUTO-RESOLVE", "reason": "Within policy.", '
            '"draft_reply": "Approved.", "policy_pages": [1]}'
        )
    )
    r = client.post("/triage", json={"ticket": "I want a refund within 7 days."})
    assert r.status_code == 200
    assert r.json()["decision"] == "AUTO-RESOLVE"


def test_app6_upload_and_mock_analysis(text_pdf, upload_pdf):
    client = TestClient(app6_main.app)
    upload_pdf(client, "/upload")

    app6_main.client = FakeGroqClient(
        FakeResponse(
            "",
            tool_calls=[
                type(
                    "ToolCall",
                    (),
                    {
                        "id": "tc_1",
                        "function": type(
                            "Function",
                            (),
                            {
                                "name": "run_python",
                                "arguments": '{"code": "print(100 - 20)"}',
                            },
                        )(),
                    },
                )()
            ],
        )
    )
    r = client.post("/analyze", json={"question": "What is revenue minus profit?"})
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert any(step["tool"] == "run_python" for step in data["agent_steps"])


def test_app6_sandbox_rejects_malicious_code(text_pdf, upload_pdf):
    client = TestClient(app6_main.app)
    upload_pdf(client, "/upload")

    app6_main.client = FakeGroqClient(
        FakeResponse(
            "",
            tool_calls=[
                type(
                    "ToolCall",
                    (),
                    {
                        "id": "tc_1",
                        "function": type(
                            "Function",
                            (),
                            {
                                "name": "run_python",
                                "arguments": '{"code": "import os\\nprint(os.getcwd())"}',
                            },
                        )(),
                    },
                )()
            ],
        )
    )
    r = client.post("/analyze", json={"question": "Try to break out."})
    assert r.status_code == 200
    data = r.json()
    python_step = next(s for s in data["agent_steps"] if s["tool"] == "run_python")
    assert python_step["error"] is True
