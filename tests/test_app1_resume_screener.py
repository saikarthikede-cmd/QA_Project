"""Regression tests for App 1 (Resume Screener) bug fixes.

Each test maps to a bug found in the code review:
  - one candidate's LLM failure no longer discards everyone's results
  - failed parses return score=None (not 0) and sort last
  - score is clamped, recommendation is derived from the score, citations are real
  - upload validation (header check, missing filename, size, duplicates)
  - GET /state lets the UI recover after a refresh
  - /screen iterates a snapshot, so a concurrent delete can't crash it
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app1_resume_screener import main as app1
from tests.test_apps import FakeLLMClient, FakeResponse

JD_TEXT = "Senior Backend Engineer. Requires Python, FastAPI, PostgreSQL, AWS, 5+ years experience."


@pytest.fixture(autouse=True)
def clean_state():
    def reset():
        app1._state.update(jd_chunks=[], jd_filename="", resumes={}, last_results=[], chat_history=[])
        app1.client = None
        app1.provider = None

    reset()
    yield
    reset()


@pytest.fixture
def api():
    return TestClient(app1.app)


def _pdf(api, text_pdf, url, name, text):
    return api.post(url, files={"file": (name, text_pdf(text), "application/pdf")})


@pytest.fixture
def loaded(api, text_pdf):
    """JD + two resumes uploaded."""
    assert _pdf(api, text_pdf, "/upload-jd", "jd.pdf", JD_TEXT).status_code == 200
    assert _pdf(api, text_pdf, "/upload-resume", "alice.pdf", "Alice Nguyen. Backend engineer with 8 years of experience building APIs in Python and FastAPI, deployed on AWS with PostgreSQL.").status_code == 200
    assert _pdf(api, text_pdf, "/upload-resume", "bob.pdf", "Bob Smith. Junior Java developer with 2 years of experience maintaining internal Spring applications and writing unit tests.").status_code == 200
    return api


def set_client(monkeypatch, api, fake):
    monkeypatch.setattr(app1, "validate_key", lambda provider, api_key: (fake, provider))
    assert api.post("/api/set-key", json={"provider": "groq", "api_key": "k"}).status_code == 200


def good(score, **extra):
    import json
    body = {"score": score, "recommendation": "Strong Match", "matched_skills": ["Python"],
            "missing_skills": [], "red_flags": [], "summary": "ok", "cited_pages": [99]}
    body.update(extra)
    return FakeResponse(json.dumps(body))


# ---------------------------------------------------------------- failure isolation

class FlakyClient(FakeLLMClient):
    """Raises on every call whose prompt mentions `bad_name`; otherwise returns the scripted response."""

    def __init__(self, response, bad_name):
        super().__init__(response)
        self.bad_name = bad_name

    def invoke(self, messages):
        if self.bad_name in str(messages[0].content):
            self.call_count += 1
            raise RuntimeError("provider exploded")
        return super().invoke(messages)


def test_one_candidate_failure_keeps_other_results(loaded, monkeypatch):
    # Every call for alice.pdf raises (agent + retry); bob.pdf succeeds.
    set_client(monkeypatch, loaded, FlakyClient(good(90), bad_name="alice.pdf"))
    r = loaded.post("/screen")
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 2
    by_name = {x["candidate"]: x for x in results}
    failed = [x for x in results if x["score"] is None]
    ok = [x for x in results if x["score"] is not None]
    assert len(failed) == 1 and len(ok) == 1
    assert failed[0]["candidate"] == "alice.pdf"
    assert failed[0]["recommendation"] == "Screening Failed"
    assert ok[0]["score"] == 90
    assert results[0]["score"] == 90, "failed candidate must sort last, not be treated as 0"
    assert set(by_name) == {"alice.pdf", "bob.pdf"}


def test_unparseable_output_is_failed_not_zero(loaded, monkeypatch):
    set_client(monkeypatch, loaded, FakeLLMClient(FakeResponse("sorry, no JSON here")))
    results = loaded.post("/screen").json()["results"]
    assert all(x["score"] is None for x in results)
    assert all(x["recommendation"] == "Screening Failed" for x in results)


def test_non_numeric_score_is_failed_not_zero(loaded, monkeypatch):
    set_client(monkeypatch, loaded, FakeLLMClient(good("high")))
    results = loaded.post("/screen").json()["results"]
    assert all(x["score"] is None for x in results)


def test_bad_api_key_still_aborts_with_401(loaded, monkeypatch):
    from openai import AuthenticationError
    import httpx

    class BadKey(FakeLLMClient):
        def invoke(self, messages):
            req = httpx.Request("POST", "https://x")
            raise AuthenticationError("bad", response=httpx.Response(401, request=req), body=None)

    set_client(monkeypatch, loaded, BadKey(good(50)))
    assert loaded.post("/screen").status_code == 401


# ---------------------------------------------------------------- result validation

@pytest.mark.parametrize("raw,expected,label", [
    (150, 100, "Strong Match"),
    (-20, 0, "Not Suitable"),
    ("72.9", 72, "Possible Match"),
    (80, 80, "Strong Match"),
    (49, 49, "Not Suitable"),
])
def test_score_clamped_and_recommendation_derived(loaded, monkeypatch, raw, expected, label):
    # Model claims a contradictory recommendation + bogus citation page 99
    set_client(monkeypatch, loaded, FakeLLMClient(good(raw, recommendation="Not Suitable" if expected >= 80 else "Strong Match")))
    results = loaded.post("/screen").json()["results"]
    for x in results:
        assert x["score"] == expected
        assert x["recommendation"] == label


def test_cited_pages_come_from_retrieval_not_model(loaded, monkeypatch):
    set_client(monkeypatch, loaded, FakeLLMClient(good(70)))
    for x in loaded.post("/screen").json()["results"]:
        assert 99 not in x["cited_pages"]
        assert x["cited_pages"] == [1]


def test_non_list_fields_normalised(loaded, monkeypatch):
    set_client(monkeypatch, loaded, FakeLLMClient(good(70, matched_skills="Python", red_flags=None)))
    for x in loaded.post("/screen").json()["results"]:
        assert x["matched_skills"] == [] and x["red_flags"] == []


def test_results_sorted_high_to_low(loaded, monkeypatch):
    scores = iter([40, 85])

    class Seq(FakeLLMClient):
        def invoke(self, messages):
            self.call_count += 1
            return good(next(scores))

    set_client(monkeypatch, loaded, Seq(good(0)))
    results = loaded.post("/screen").json()["results"]
    assert [x["score"] for x in results] == [85, 40]


# ---------------------------------------------------------------- upload validation

def test_resume_blocked_until_jd(api, text_pdf):
    assert _pdf(api, text_pdf, "/upload-resume", "a.pdf", "x").status_code == 400


def test_non_pdf_extension_rejected(api):
    assert api.post("/upload-jd", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 400


def test_fake_pdf_without_header_rejected(api):
    r = api.post("/upload-jd", files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")})
    assert r.status_code == 400
    assert "valid PDF" in r.json()["detail"]


def test_missing_filename_rejected_cleanly(api):
    r = api.post("/upload-jd", files={"file": ("", b"%PDF-1.4", "application/pdf")})
    assert r.status_code in (400, 422)  # never a 500 AttributeError


def test_oversize_rejected(api, monkeypatch):
    monkeypatch.setattr(app1, "MAX_UPLOAD_BYTES", 10)
    r = api.post("/upload-jd", files={"file": ("big.pdf", b"%PDF-" + b"0" * 100, "application/pdf")})
    assert r.status_code == 413


def test_duplicate_resume_rejected(loaded, text_pdf):
    assert _pdf(loaded, text_pdf, "/upload-resume", "alice.pdf", "again").status_code == 400


def test_question_too_long_rejected(loaded, monkeypatch):
    set_client(monkeypatch, loaded, FakeLLMClient(FakeResponse("a")))
    r = loaded.post("/ask", json={"question": "x" * (app1.MAX_QUESTION_CHARS + 1)})
    assert r.status_code == 400


# ---------------------------------------------------------------- state / staleness

def test_state_endpoint_reflects_server(loaded, monkeypatch):
    s = loaded.get("/state").json()
    assert s["jd_filename"] == "jd.pdf"
    assert sorted(s["resumes"]) == ["alice.pdf", "bob.pdf"]
    assert s["last_results"] == []

    set_client(monkeypatch, loaded, FakeLLMClient(good(75)))
    loaded.post("/screen")
    assert len(loaded.get("/state").json()["last_results"]) == 2


def test_state_empty_on_fresh_server(api):
    s = api.get("/state").json()
    assert s == {"jd_filename": "", "resumes": [], "last_results": []}


def test_adding_or_removing_resume_clears_stale_results(loaded, monkeypatch, text_pdf):
    set_client(monkeypatch, loaded, FakeLLMClient(good(75)))
    loaded.post("/screen")
    assert loaded.get("/state").json()["last_results"]
    _pdf(loaded, text_pdf, "/upload-resume", "carol.pdf", "Carol Diaz. Go developer with 4 years of experience building microservices and command line tooling for infrastructure teams.")
    assert loaded.get("/state").json()["last_results"] == []

    loaded.post("/screen")
    assert loaded.delete("/resumes/carol.pdf").status_code == 200
    assert loaded.get("/state").json()["last_results"] == []


def test_new_jd_resets_everything(loaded, text_pdf):
    _pdf(loaded, text_pdf, "/upload-jd", "jd2.pdf", "Data Scientist role. Requires Python, machine learning, statistics, and 3+ years of experience shipping models to production.")
    s = loaded.get("/state").json()
    assert s["jd_filename"] == "jd2.pdf" and s["resumes"] == []


def test_delete_unknown_resume_404(loaded):
    assert loaded.delete("/resumes/nope.pdf").status_code == 404


def test_screen_requires_key(loaded):
    assert loaded.post("/screen").status_code == 401


# ---------------------------------------------------------------- concurrency

def test_delete_during_screen_does_not_crash(loaded, monkeypatch):
    """Deleting a resume mid-run used to raise 'dictionary changed size during iteration'."""
    calls = {"n": 0}

    class DeletingClient(FakeLLMClient):
        def invoke(self, messages):
            self.call_count += 1
            if calls["n"] == 0:
                calls["n"] += 1
                app1._state["resumes"].pop("bob.pdf", None)  # simulate concurrent DELETE
            return good(60)

    set_client(monkeypatch, loaded, DeletingClient(good(60)))
    r = loaded.post("/screen")
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2  # screened the snapshot taken at start


# ---------------------------------------------------------------- /ask with failed candidates

def test_ask_handles_failed_candidate_score(loaded, monkeypatch):
    app1._state["last_results"] = [
        {"candidate": "alice.pdf", "score": None, "semantic_score": 0.0, "recommendation": "Screening Failed",
         "matched_skills": [], "missing_skills": []},
    ]
    fake = FakeLLMClient(FakeResponse("answer"))
    seen = {}
    orig = fake.invoke

    def spy(messages):
        seen["prompt"] = messages[0].content
        return orig(messages)

    fake.invoke = spy
    set_client(monkeypatch, loaded, fake)
    r = loaded.post("/ask", json={"question": "Who is best?"})
    assert r.status_code == 200
    assert "None/100" not in seen["prompt"]
    assert "screening failed" in seen["prompt"]
