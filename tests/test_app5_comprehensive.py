"""Comprehensive test suite for App 5 (Policy Triage Agent).
Tests key status, session caching, SLA & sentiment tools, robust citation parsing,
and triage/ask API endpoints.
"""
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from app5_policy_triage import main as app5_main
from shared.pdf_utils import Chunk
from tests.test_apps import FakeResponse, set_fake_key


@pytest.fixture
def upload_pdf_fixture(text_pdf):
    def _upload(client, endpoint="/upload"):
        pdf = text_pdf("Refund policy allows returns within 30 days. Contact support for billing issues.")
        return client.post(endpoint, files={"file": ("policy.pdf", pdf, "application/pdf")})
    return _upload


@pytest.fixture(autouse=True)
def reset_app5_state(tmp_path, monkeypatch):
    """Ensure clean module state and isolated cache directory for each test."""
    app5_main._state = {"chunks": [], "filename": "", "last_result": None, "chat_history": []}
    cache_dir = tmp_path / ".rag_cache"
    monkeypatch.setattr(app5_main, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(app5_main, "CACHE_FILE", cache_dir / "last_policy_upload.pkl")
    yield
    app5_main._state = {"chunks": [], "filename": "", "last_result": None, "chat_history": []}


def test_app5_key_status_endpoint(monkeypatch):
    client = TestClient(app5_main.app)
    monkeypatch.setattr(app5_main, "client", None)
    monkeypatch.setattr(app5_main, "provider", None)
    monkeypatch.setattr(app5_main, "init_from_env", lambda: (None, None))

    r = client.get("/api/key-status")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False

    monkeypatch.setattr(app5_main, "client", MagicMock())
    monkeypatch.setattr(app5_main, "provider", "gemini")
    r2 = client.get("/api/key-status")
    assert r2.status_code == 200
    assert r2.json()["configured"] is True
    assert r2.json()["provider"] == "gemini"


def test_app5_session_persistence():
    client = TestClient(app5_main.app)

    # Initial session is empty
    r = client.get("/session")
    assert r.status_code == 200
    data = r.json()
    assert data["filename"] == ""
    assert data["chunks"] == 0

    # Simulate loaded state and cache save
    chunk1 = Chunk(text="Refunds within 14 days", page=1, source="policy.pdf")
    app5_main._state["chunks"] = [chunk1]
    app5_main._state["filename"] = "policy.pdf"
    app5_main._state["last_result"] = {
        "decision": "AUTO-RESOLVE",
        "reason": "Within 14-day window",
        "draft_reply": "Your refund is approved.",
        "policy_pages": [1]
    }
    app5_main._state["chat_history"] = [{"question": "What is the policy?", "answer": "14 days."}]
    app5_main._save_policy_cache()

    # Clear in-memory state
    app5_main._state = {"chunks": [], "filename": "", "last_result": None, "chat_history": []}

    # /session endpoint triggers _ensure_policy_loaded and restores state
    r2 = client.get("/session")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["filename"] == "policy.pdf"
    assert d2["chunks"] == 1
    assert d2["last_result"]["decision"] == "AUTO-RESOLVE"
    assert len(d2["chat_history"]) == 1


def test_app5_extract_pages_from_text():
    # List of ints
    assert app5_main._extract_pages_from_text([1, 2], max_page=5) == [1, 2]

    # Range list item
    assert app5_main._extract_pages_from_text(["1-3"], max_page=5) == [1, 2, 3]

    # String with word "to"
    assert app5_main._extract_pages_from_text("Pages 2 to 4", max_page=10) == [2, 3, 4]

    # String with comma
    assert app5_main._extract_pages_from_text("1, 3, 5", max_page=10) == [1, 3, 5]

    # Out of bounds page excluded
    assert app5_main._extract_pages_from_text([1, 99], max_page=10) == [1]

    # Scans prose context when raw_pages is empty
    text = "Refer to page 2 and p. 4 for dispute procedures."
    assert app5_main._extract_pages_from_text([], text_context=text, max_page=10) == [2, 4]


def test_app5_sla_lookup_and_synonyms():
    # Direct category
    res_sec = app5_main.run_tool("check_sla_status", {"issue_type": "security"})
    assert "IMMEDIATE" in res_sec and "security" in res_sec

    # Synonym mapping
    res_refund = app5_main.run_tool("check_sla_status", {"issue_type": "refund dispute"})
    assert "billing" in res_refund

    res_law = app5_main.run_tool("check_sla_status", {"issue_type": "threat of lawsuit"})
    assert "Legal" in res_law

    res_hack = app5_main.run_tool("check_sla_status", {"issue_type": "account got hacked"})
    assert "security" in res_hack

    # Fallback category
    res_gen = app5_main.run_tool("check_sla_status", {"issue_type": "other question"})
    assert "general" in res_gen


def test_app5_sentiment_classifier():
    # Neutral text
    res_neutral = app5_main.run_tool("classify_sentiment", {"text": "I would like to check my order status please."})
    assert "NEUTRAL" in res_neutral

    # Mild negative
    res_mild = app5_main.run_tool("classify_sentiment", {"text": "I am slightly frustrated with this delay."})
    assert "NEGATIVE (mild)" in res_mild

    # High negative with multiple keywords
    res_high = app5_main.run_tool("classify_sentiment", {"text": "This is unacceptable fraud and I am consulting my lawyer for a lawsuit!"})
    assert "NEGATIVE (high)" in res_high


def test_app5_escalate_tool():
    res = app5_main.run_tool("escalate_to_human", {"reason": "Customer threatened litigation"})
    assert "litigation" in res
    assert "human escalation" in res


def test_app5_ask_out_of_scope_empty_pages(text_pdf, upload_pdf_fixture, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf_fixture(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse("This information is not covered in the policy document."))

    r = client.post("/ask", json={"question": "What is the CEO's personal email?"})
    assert r.status_code == 200
    data = r.json()
    assert data["pages"] == []


def test_app5_ask_with_page_citations(text_pdf, upload_pdf_fixture, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf_fixture(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse("As stated on page 1, return policy is 30 days."))

    r = client.post("/ask", json={"question": "What is the return policy?"})
    assert r.status_code == 200
    data = r.json()
    assert data["pages"] == [1]


def test_app5_triage_auto_resolve(text_pdf, upload_pdf_fixture, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf_fixture(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse(
        '{"decision": "AUTO-RESOLVE", "reason": "Within policy window.", '
        '"draft_reply": "Approved.", "policy_pages": [1]}'
    ))

    r = client.post("/triage", json={"ticket": "I want a refund within 3 days."})
    assert r.status_code == 200
    data = r.json()
    assert data["decision"] == "AUTO-RESOLVE"
    assert data["policy_pages"] == [1]


def test_app5_triage_escalation(text_pdf, upload_pdf_fixture, monkeypatch):
    client = TestClient(app5_main.app)
    upload_pdf_fixture(client, "/upload")

    set_fake_key(monkeypatch, app5_main, client, FakeResponse(
        '{"decision": "ESCALATE", "reason": "Customer alleges account compromise.", '
        '"draft_reply": "We have escalated this to our security team.", "policy_pages": [1]}'
    ))

    r = client.post("/triage", json={"ticket": "My account was compromised last night."})
    assert r.status_code == 200
    data = r.json()
    assert data["decision"] == "ESCALATE"
    assert "security" in data["draft_reply"].lower()
    assert data["policy_pages"] == [1]
