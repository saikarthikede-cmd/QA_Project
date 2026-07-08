"""Per-browser-session LLM client storage.

v2 design: two testers hitting the *same running app container* each get
their own signed session cookie (Starlette's SessionMiddleware) and their
own {client, provider} slot here, keyed by a session id carried in that
cookie. This replaces v1's single process-global client/provider, which one
tester's /api/set-key call would silently overwrite for everyone else on
that container.

ponytail: capped at MAX_SESSIONS with oldest-first eviction instead of a
real TTL/idle-expiry — good enough to bound memory for a QA demo tool; add
expiry-based cleanup if this ever runs as a long-lived multi-tenant service.
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Optional

import openai
from starlette.requests import Request

MAX_SESSIONS = 200

_sessions: "OrderedDict[str, dict]" = OrderedDict()


def _session_id(request: Request) -> str:
    sid = request.session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        request.session["sid"] = sid
    return sid


def get_client(request: Request) -> Optional[openai.OpenAI]:
    return _sessions.get(_session_id(request), {}).get("client")


def get_provider(request: Request) -> Optional[str]:
    return _sessions.get(_session_id(request), {}).get("provider")


def set_session(request: Request, client: openai.OpenAI, provider: str) -> None:
    sid = _session_id(request)
    _sessions[sid] = {"client": client, "provider": provider}
    _sessions.move_to_end(sid)
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
