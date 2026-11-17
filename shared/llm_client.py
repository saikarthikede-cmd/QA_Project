"""Lets each app's user supply their own Groq, OpenAI or Gemini key at runtime
via a popup, instead of a key baked into .env. All providers are called through
LangChain's ChatOpenAI — Groq and Gemini both expose OpenAI-compatible
endpoints, so one client shape covers chat completions, tool calling, and JSON
mode for any of them.
Every call site overrides the model per-call via `.bind(model=...)` since
different apps/tiers need different models from the same client.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

import openai
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# gemini-2.5-flash was shut down by Google on 2026-10-16; override with the GEMINI_MODEL
# env var if Google retires this one too (https://ai.google.dev/gemini-api/docs/deprecations).
GEMINI_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
DISPLAY_NAME = {"groq": "Groq", "openai": "OpenAI", "gemini": "Gemini"}
PROVIDERS = {
    "groq": (GROQ_DEFAULT_MODEL, GROQ_BASE_URL),
    "openai": (OPENAI_DEFAULT_MODEL, None),
    "gemini": (GEMINI_DEFAULT_MODEL, GEMINI_BASE_URL),
}


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str


def validate_key(provider: str, api_key: str) -> Tuple[ChatOpenAI, str]:
    """Build a LangChain ChatOpenAI client for `provider` and confirm the key
    actually works.

    Raises ValueError (safe to show the user) on a bad provider, empty key,
    rejected key, or unreachable API.
    """
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider!r}. Choose Groq, OpenAI or Gemini.")
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API key is required.")

    default_model, base_url = PROVIDERS[provider]
    client = ChatOpenAI(
        model=default_model,
        api_key=api_key,
        base_url=base_url,
        timeout=45.0,
        max_retries=1,  # SDK default is 2; each retry multiplies worst-case wait on a slow/rate-limited provider
        temperature=0,
    )
    name = DISPLAY_NAME[provider]
    try:
        client.root_client.models.list()  # cheap real call — fails fast on a bad/revoked key
    except openai.AuthenticationError:
        raise ValueError(f"{name} rejected this key — check it and try again.")
    except openai.APIConnectionError:
        raise ValueError(f"Could not reach {name}. Check your network and try again.")
    except openai.APIStatusError as e:
        raise ValueError(f"{name} returned an error validating this key: {e.message}")

    return client, provider


def resolve_model(provider: Optional[str], groq_model: str) -> str:
    """Map a Groq model name to whatever this session's active provider needs.

    ponytail: one fixed model per non-Groq provider regardless of which Groq
    tier was requested — good enough for a QA demo; add per-tier mapping if
    answer quality needs to differ between the "fast" and "smart" tiers.
    """
    if provider == "openai":
        return OPENAI_DEFAULT_MODEL
    if provider == "gemini":
        return GEMINI_DEFAULT_MODEL
    return groq_model
