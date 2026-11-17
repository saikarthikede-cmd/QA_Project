"""Comprehensive tests for App 3 – FAQ Generator."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app3_faq_generator import main as app3_main
from tests.test_apps import FakeResponse, set_fake_key


@pytest.fixture
def upload_pdf_fixture(text_pdf):
    def _upload(client, endpoint="/upload"):
        pdf = text_pdf("SmartPay is a cloud-based payment processing gateway. Standard settlement takes 2 business days.")
        return client.post(endpoint, files={"file": ("smartpay.pdf", pdf, "application/pdf")})
    return _upload


def test_app3_extract_pages_helper():
    assert app3_main._extract_pages_from_answer("Found on Page 1.", max_page=5) == [1]
    assert app3_main._extract_pages_from_answer("See Pages 1 and 2.", max_page=5) == [1, 2]
    assert app3_main._extract_pages_from_answer("Covered in pages 1-3.", max_page=5) == [1, 2, 3]
    assert app3_main._extract_pages_from_answer("Out of scope. Not found.", max_page=5) == []
    # Clamps to max_page
    assert app3_main._extract_pages_from_answer("Page 99.", max_page=3) == []


def test_app3_generate_more_appends_and_avoids(text_pdf, upload_pdf_fixture, monkeypatch, tmp_path):
    client = TestClient(app3_main.app)
    monkeypatch.setattr(app3_main, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(app3_main, "CACHE_FILE", tmp_path / "last_upload.pkl")

    upload_pdf_fixture(client, "/upload")

    # Initial generate
    set_fake_key(
        monkeypatch,
        app3_main,
        client,
        FakeResponse('{"faqs": [{"question": "What is the return policy?", "answer": "30 days.", "page": 1}]}'),
    )
    r = client.post("/generate")
    assert r.status_code == 200
    assert len(r.json()["faqs"]) == 1

    # Generate more
    set_fake_key(
        monkeypatch,
        app3_main,
        client,
        FakeResponse('{"faqs": [{"question": "What are the fees?", "answer": "1.9% per txn.", "page": 1}]}'),
    )
    r = client.post("/generate-more")
    assert r.status_code == 200
    data = r.json()
    assert data["new_count"] == 1
    assert data["total"] == 2
    assert len(data["faqs"]) == 2


def test_app3_regenerate_single_faq(text_pdf, upload_pdf_fixture, monkeypatch, tmp_path):
    client = TestClient(app3_main.app)
    monkeypatch.setattr(app3_main, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(app3_main, "CACHE_FILE", tmp_path / "last_upload.pkl")

    upload_pdf_fixture(client, "/upload")

    set_fake_key(
        monkeypatch,
        app3_main,
        client,
        FakeResponse(
            '{"faqs": ['
            '{"question": "Q1", "answer": "A1", "page": 1}, '
            '{"question": "Q2", "answer": "A2", "page": 1}'
            ']}'
        ),
    )
    client.post("/generate")

    # Regenerate index 1
    set_fake_key(
        monkeypatch,
        app3_main,
        client,
        FakeResponse('{"faqs": [{"question": "Q2_new", "answer": "A2_new", "page": 1}]}'),
    )
    r = client.post("/regenerate", json={"index": 1})
    assert r.status_code == 200
    data = r.json()
    assert data["index"] == 1
    assert data["faq"]["question"] == "Q2_new"

    # Confirm list in state has Q1 and Q2_new
    r = client.get("/faqs")
    assert r.status_code == 200
    faqs = r.json()["faqs"]
    assert len(faqs) == 2
    assert faqs[0]["question"] == "Q1"
    assert faqs[1]["question"] == "Q2_new"


def test_app3_ask_returns_empty_pages_on_not_found(text_pdf, monkeypatch, tmp_path):
    client = TestClient(app3_main.app)
    monkeypatch.setattr(app3_main, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(app3_main, "CACHE_FILE", tmp_path / "last_upload.pkl")

    pdf_bytes = text_pdf("SmartPay payment processing gateway setup and limits.")
    r = client.post("/upload", files={"file": ("smartpay.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 200

    set_fake_key(
        monkeypatch,
        app3_main,
        client,
        FakeResponse("This information is not found in the document."),
    )
    r = client.post("/ask", json={"question": "What is the refund policy?"})
    assert r.status_code == 200
    data = r.json()
    assert "not found in the document" in data["answer"]
    assert data["pages"] == []
