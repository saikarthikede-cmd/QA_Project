"""Lets each app's user supply their own Groq or OpenAI key at runtime via a
popup, instead of a key baked into .env. Both providers are called through
the `openai` SDK — Groq exposes an OpenAI-compatible endpoint, so one client
shape covers chat completions, tool calling, and JSON mode for either.
"""
from __future__ import annotations

from typing import Optional, Tuple

import openai
from pydantic import BaseModel

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
DISPLAY_NAME = {"groq": "Groq", "openai": "OpenAI"}


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str


def validate_key(provider: str, api_key: str) -> Tuple[openai.OpenAI, str]:
    """Build a client for `provider` and confirm the key actually works.

    Raises ValueError (safe to show the user) on a bad provider, empty key,
    rejected key, or unreachable API.
    """
    provider = (provider or "").strip().lower()
    if provider not in ("groq", "openai"):
        raise ValueError(f"Unsupported provider: {provider!r}. Choose Groq or OpenAI.")
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API key is required.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url=GROQ_BASE_URL if provider == "groq" else None,
        timeout=30.0,
    )
    name = DISPLAY_NAME[provider]
    try:
        client.models.list()  # cheap real call — fails fast on a bad/revoked key
    except openai.AuthenticationError:
        raise ValueError(f"{name} rejected this key — check it and try again.")
    except openai.APIConnectionError:
        raise ValueError(f"Could not reach {name}. Check your network and try again.")
    except openai.APIStatusError as e:
        raise ValueError(f"{name} returned an error validating this key: {e.message}")

    return client, provider


def resolve_model(provider: Optional[str], groq_model: str) -> str:
    """Map a Groq model name to whatever this session's active provider needs.

    ponytail: one fixed OpenAI model regardless of which Groq tier was
    requested — good enough for a QA demo; add per-tier mapping if answer
    quality on OpenAI needs to differ between the "fast" and "smart" tiers.
    """
    return OPENAI_DEFAULT_MODEL if provider == "openai" else groq_model
