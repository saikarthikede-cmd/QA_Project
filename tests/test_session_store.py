"""Unit tests for shared/session_store.py (v2's per-session key storage)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.session_store import get_client, get_provider, set_session


class FakeRequest:
    """Stand-in for starlette.requests.Request — only `.session` (a dict) is used."""

    def __init__(self):
        self.session = {}


def test_two_sessions_do_not_share_state():
    r1, r2 = FakeRequest(), FakeRequest()
    set_session(r1, "client-A", "groq")
    set_session(r2, "client-B", "openai")

    assert get_client(r1) == "client-A"
    assert get_provider(r1) == "groq"
    assert get_client(r2) == "client-B"
    assert get_provider(r2) == "openai"


def test_unset_session_has_no_client():
    r = FakeRequest()
    assert get_client(r) is None
    assert get_provider(r) is None


def test_same_session_id_persists_across_requests():
    r1 = FakeRequest()
    set_session(r1, "client-A", "groq")
    sid = r1.session["sid"]

    r2 = FakeRequest()
    r2.session["sid"] = sid  # simulates the browser resending the same cookie
    assert get_client(r2) == "client-A"
