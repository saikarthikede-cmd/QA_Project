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
        validate_key("cohere", "some-key")


def test_validate_key_rejects_empty_key():
    with pytest.raises(ValueError, match="API key is required"):
        validate_key("groq", "   ")


def test_resolve_model_passes_through_for_groq_or_unset():
    assert resolve_model("groq", "llama-3.1-8b-instant") == "llama-3.1-8b-instant"
    assert resolve_model(None, "llama-3.1-8b-instant") == "llama-3.1-8b-instant"


def test_resolve_model_maps_to_openai_default():
    assert resolve_model("openai", "llama-3.1-8b-instant") == "gpt-4o-mini"


def test_resolve_model_maps_to_gemini_default():
    assert resolve_model("gemini", "llama-3.1-8b-instant") == "gemini-flash-latest"


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
    assert seen["model"] == "gemini-flash-latest"
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


def test_resolve_model_maps_to_claude_and_codevector():
    assert resolve_model("claude", "llama-3.1-8b-instant") == "claude-3-5-sonnet-20241022"
    assert resolve_model("anthropic", "llama-3.1-8b-instant") == "claude-3-5-sonnet-20241022"
    assert resolve_model("codevector", "llama-3.1-8b-instant") == "kimi-k-2-7-code"


def test_round_robin_rotation():
    from shared.llm_client import RoundRobinChatClient

    class MockClient:
        def __init__(self, key):
            self.key = key
        def invoke(self, inp, **kw):
            return f"{self.key}: {inp}"

    c1 = MockClient("k1")
    c2 = MockClient("k2")
    rr = RoundRobinChatClient(clients=[c1, c2], keys=["k1", "k2"], provider="openai")

    assert rr.invoke("call1") == "k1: call1"
    assert rr.invoke("call2") == "k2: call2"
    assert rr.invoke("call3") == "k1: call3"


def test_round_robin_failover_on_error():
    from shared.llm_client import RoundRobinChatClient

    class FlakyClient:
        def __init__(self, key, fail=False):
            self.key = key
            self.fail = fail
        def invoke(self, inp, **kw):
            if self.fail:
                raise RuntimeError("Rate limit 429")
            return f"success from {self.key}"

    c1 = FlakyClient("k1", fail=True)
    c2 = FlakyClient("k2", fail=False)
    rr = RoundRobinChatClient(clients=[c1, c2], keys=["k1", "k2"], provider="groq")

    # c1 fails on call1, automatically fails over to c2
    result = rr.invoke("test")
    assert result == "success from k2"


def test_init_from_env_detects_keys(monkeypatch):
    from shared import llm_client

    monkeypatch.setenv("GROQ_API_KEY", "test-key-1, test-key-2")
    client, provider = llm_client.init_from_env()
    assert client is not None
    assert provider == "groq"
    assert len(client.clients) == 2

