"""Shared LLM-call error handling for all six apps.

All providers (Groq, OpenAI, Gemini, Claude, CodeVector) are handled cleanly with
consistent HTTP status codes and user-friendly error messages.
"""
from __future__ import annotations

import traceback

from fastapi import HTTPException
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

try:
    import anthropic
except ImportError:
    anthropic = None


def require_client(client) -> None:
    """Fail fast with a clear 401 instead of an AttributeError deep in a call chain."""
    if client is None:
        raise HTTPException(401, "No LLM key set for this session. Refresh the page and enter your API key.")


def raise_for_groq_error(e: Exception) -> None:
    """Convert an exception raised while calling the LLM into the right HTTPException.

    Always raises. HTTPExceptions (e.g. a deliberate 400/422/502 raised
    earlier in the same try block) pass through unchanged instead of being
    flattened into a generic 500.
    """
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, AuthenticationError) or (anthropic and isinstance(e, anthropic.AuthenticationError)):
        raise HTTPException(401, "Your API key was rejected. Refresh the page and enter a valid key.")
    if isinstance(e, RateLimitError) or (anthropic and isinstance(e, anthropic.RateLimitError)):
        raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
    if (
        isinstance(e, (InternalServerError, APIConnectionError, APITimeoutError))
        or (anthropic and isinstance(e, (anthropic.InternalServerError, anthropic.APIConnectionError, anthropic.APITimeoutError)))
        or getattr(e, "status_code", None) in (500, 502, 503, 504)
        or "high demand" in str(e).lower()
        or "spikes in demand" in str(e).lower()
        or "unavailable" in str(e).lower()
        or "overloaded" in str(e).lower()
    ):
        raise HTTPException(503, "The AI model is currently experiencing high demand. Please try again in a few moments.")
    raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
