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


def test_require_client_blocks_when_unset():
    with pytest.raises(HTTPException) as exc_info:
        require_client(None)
    assert exc_info.value.status_code == 401


def test_require_client_allows_when_set():
    require_client(object())  # must not raise
