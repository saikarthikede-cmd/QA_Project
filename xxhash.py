"""Pure-Python fallback for environments that block the native xxhash wheel.

LangSmith imports only ``xxh3_128(...).digest()`` during the LangChain startup
path used by these demo apps. Some locked-down Windows machines block
``xxhash._xxhash`` at DLL load time, which prevents the FastAPI apps from even
starting. This local module shadows the optional native dependency and provides
the small API surface LangSmith needs.
"""
from __future__ import annotations

import hashlib


class _Hash128:
    def __init__(self, data: bytes = b""):
        self._data = bytes(data)

    def digest(self) -> bytes:
        return hashlib.blake2b(self._data, digest_size=16).digest()


def xxh3_128(data: bytes = b"") -> _Hash128:
    return _Hash128(data)
