"""Shared Groq-call error handling for all six apps.

Replaces the old `type(e).__name__ == "RateLimitError"` string comparisons
(fragile — breaks if the SDK restructures its exceptions, or misfires on an
unrelated class that happens to share the name) with a real isinstance check
against the SDK's own exception type.
"""
from __future__ import annotations

import traceback

from fastapi import HTTPException
from groq import RateLimitError


def raise_for_groq_error(e: Exception) -> None:
    """Convert an exception raised while calling Groq into the right HTTPException.

    Always raises. HTTPExceptions (e.g. a deliberate 400/422/502 raised
    earlier in the same try block) pass through unchanged instead of being
    flattened into a generic 500.
    """
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, RateLimitError):
        raise HTTPException(429, "Rate limit reached on the AI provider. Please wait about 10 seconds and try again.")
    raise HTTPException(500, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
