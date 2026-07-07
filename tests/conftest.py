"""Shared pytest fixtures and helpers."""
from __future__ import annotations

import io
from typing import Callable

import pytest
from fpdf import FPDF


def make_text_pdf(text: str, title: str = "Test Document") -> bytes:
    """Create a simple text-based PDF in memory."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for line in text.split("\n"):
        pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    buffer = io.BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


@pytest.fixture
def text_pdf() -> Callable[[str], bytes]:
    return make_text_pdf


class FakeGroqChoice:
    def __init__(self, content: str):
        self.message = type("Message", (), {"content": content, "tool_calls": None})()


class FakeGroqResponse:
    def __init__(self, content: str):
        self.choices = [FakeGroqChoice(content)]


@pytest.fixture
def mock_groq_client(monkeypatch):
    """Patch Groq client so LLM endpoints return predictable JSON without network calls."""

    def _patch(module, response_content: str):
        fake_response = FakeGroqResponse(response_content)

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            class chat:
                class completions:
                    @staticmethod
                    def create(*args, **kwargs):
                        return fake_response

        monkeypatch.setattr(module, "client", FakeClient())

    return _patch
