"""Shared LLM-call error handling for all six apps.

Both providers (Groq, OpenAI) are called through the `openai` SDK — Groq's
endpoint is OpenAI-compatible — so one set of exception types covers either.
"""
from __future__ import annotations

import traceback

from fastapi import HTTPException
from openai import AuthenticationError, RateLimitError


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
    if isinstance(e, AuthenticationError):
        raise HTTPException(401, "Your API key was rejected. Refresh the page and enter a valid key.")
    if isinstance(e, RateLimitError):
        raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
    raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
