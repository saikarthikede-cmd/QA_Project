"""End-to-end proof that v2's session-scoped key store actually isolates
concurrent browser sessions hitting the same running app — and an honest
check on what it does NOT isolate (uploaded documents, chat history: those
still live in each app's single global `_state` dict, shared by everyone
hitting that container, exactly as in v1).
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app1_resume_screener import main as app1_main
from tests.test_apps import FakeLLMClient, FakeResponse


def test_two_browser_sessions_get_independent_llm_clients(text_pdf, monkeypatch):
    client_a = TestClient(app1_main.app)  # separate cookie jar = separate "browser"
    client_b = TestClient(app1_main.app)

    jd_bytes = text_pdf(
        "Senior Backend Engineer. Requires Python, FastAPI, PostgreSQL, AWS, 5+ years experience."
    )
    resume_bytes = text_pdf(
        "Sarah Chen. 8 years experience. Python, FastAPI, PostgreSQL, AWS, Kubernetes."
    )
    client_a.post("/upload-jd", files={"file": ("jd.pdf", jd_bytes, "application/pdf")})
    client_a.post("/upload-resume", files={"file": ("resume.pdf", resume_bytes, "application/pdf")})

    responses_by_key = {
        "key-a": FakeResponse(
            '{"score": 11, "recommendation": "Strong Match", "matched_skills": [], '
            '"missing_skills": [], "red_flags": [], "summary": "s", "cited_pages": [1]}'
        ),
        "key-b": FakeResponse(
            '{"score": 77, "recommendation": "Strong Match", "matched_skills": [], '
            '"missing_skills": [], "red_flags": [], "summary": "s", "cited_pages": [1]}'
        ),
    }

    def fake_validate_key(provider, api_key):
        return FakeLLMClient(responses_by_key[api_key]), provider

    monkeypatch.setattr(app1_main, "validate_key", fake_validate_key)

    assert client_a.post("/api/set-key", json={"provider": "groq", "api_key": "key-a"}).status_code == 200
    assert client_b.post("/api/set-key", json={"provider": "groq", "api_key": "key-b"}).status_code == 200

    # Both sessions see the same uploaded JD/resume — _state is still one
    # global dict, NOT session-scoped. Only the LLM client/provider is.
    score_a = client_a.post("/screen").json()["results"][0]["score"]
    score_b = client_b.post("/screen").json()["results"][0]["score"]

    assert score_a == 11, "session A must use its own key's client, not session B's"
    assert score_b == 77, "session B must use its own key's client, not session A's"


def test_uploaded_documents_are_not_session_scoped(text_pdf, monkeypatch):
    """Documents (_state) remain a single global shared by every session on
    this container — v2 only isolates the API key, not the app's data. A
    second tester's upload silently replaces the first tester's document."""
    client_a = TestClient(app1_main.app)
    client_b = TestClient(app1_main.app)

    jd_a = text_pdf("Job description from tester A. Requires Python and five years of experience.")
    jd_b = text_pdf("Job description from tester B. Requires Java and three years of experience.")
    client_a.post("/upload-jd", files={"file": ("a.pdf", jd_a, "application/pdf")})
    client_b.post("/upload-jd", files={"file": ("b.pdf", jd_b, "application/pdf")})

    # Tester A's own follow-up request now sees tester B's filename —
    # proof that _state is shared, not per-session.
    resume_bytes = text_pdf("Some candidate resume with enough text to pass the scanned-PDF check.")
    r = client_a.post("/upload-resume", files={"file": ("r.pdf", resume_bytes, "application/pdf")})
    assert r.status_code == 200
    assert app1_main._state["jd_filename"] == "b.pdf"
