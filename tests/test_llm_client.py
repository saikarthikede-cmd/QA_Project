"""Unit tests for the runtime provider/key picker (shared/llm_client.py,
shared/errors.py:require_client). No live API calls — only the validation
that happens before any network request is exercised here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.errors import require_client
from shared.llm_client import resolve_model, validate_key


def test_validate_key_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported provider"):
        validate_key("anthropic", "some-key")


def test_validate_key_rejects_empty_key():
    with pytest.raises(ValueError, match="API key is required"):
        validate_key("groq", "   ")


def test_resolve_model_passes_through_for_groq_or_unset():
    assert resolve_model("groq", "llama-3.1-8b-instant") == "llama-3.1-8b-instant"
    assert resolve_model(None, "llama-3.1-8b-instant") == "llama-3.1-8b-instant"


def test_resolve_model_maps_to_openai_default():
    assert resolve_model("openai", "llama-3.1-8b-instant") == "gpt-4o-mini"


def test_resolve_model_maps_to_gemini_default():
    assert resolve_model("gemini", "llama-3.1-8b-instant") == "gemini-3.5-flash"


def test_validate_key_gemini_uses_google_endpoint(monkeypatch):
    from shared import llm_client

    class FakeModels:
        def list(self):
            return []

    class FakeRoot:
        models = FakeModels()

    seen = {}

    class FakeChat:
        def __init__(self, **kw):
            seen.update(kw)
            self.root_client = FakeRoot()

    monkeypatch.setattr(llm_client, "ChatOpenAI", FakeChat)
    client, provider = llm_client.validate_key("Gemini", "  AIza-test  ")
    assert provider == "gemini"
    assert seen["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert seen["model"] == "gemini-3.5-flash"
    assert seen["api_key"] == "AIza-test"


def test_validate_key_error_mentions_gemini():
    with pytest.raises(ValueError, match="Gemini"):
        validate_key("nope", "k")


def test_require_client_blocks_when_unset():
    with pytest.raises(HTTPException) as exc_info:
        require_client(None)
    assert exc_info.value.status_code == 401


def test_require_client_allows_when_set():
    require_client(object())  # must not raise
