"""Pure-Python fallback for environments that block the native jiter wheel.

The OpenAI SDK imports ``jiter.from_json`` from its streaming helpers. These
apps use ordinary non-streaming LangChain calls, but the import still happens
on startup. Some managed Windows machines block the native ``jiter`` DLL, so
this local module provides the small compatible function needed to import the
SDK cleanly.
"""
from __future__ import annotations

import json
from typing import Any


def from_json(data: bytes | bytearray | str, *, partial_mode: bool = False) -> Any:
    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if not partial_mode:
            raise
        return None
