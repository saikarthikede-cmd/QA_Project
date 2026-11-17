"""Live smoke test: plain chat, JSON mode, and tool calling per provider.

Usage (keys come from .env / environment, same names as .env.example):
    uv run python scripts/smoke_providers.py [groq gemini ...]
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import dotenv  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from shared.llm_client import PROVIDERS, resolve_model, validate_key  # noqa: E402

dotenv.load_dotenv(Path(__file__).parent.parent / ".env")
ENV = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY",
       "claude": "ANTHROPIC_API_KEY", "codevector": "CODEVECTOR_API_KEY"}
TOOLS = [{"type": "function", "function": {
    "name": "add", "description": "Add two integers",
    "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                   "required": ["a", "b"]}}}]


def check(label, fn):
    t = time.time()
    try:
        out = fn()
        print(f"  PASS {label} ({time.time() - t:.1f}s): {out}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL {label} ({time.time() - t:.1f}s): {type(e).__name__}: {str(e)[:300]}")


for prov in sys.argv[1:] or list(ENV):
    key = os.environ.get(ENV[prov], "").strip()
    if not key:
        print(f"[{prov}] SKIP (no {ENV[prov]})")
        continue
    model = resolve_model(prov, PROVIDERS["groq"][0])
    print(f"[{prov}] model={model}")
    try:
        client, _ = validate_key(prov, key)
        print("  PASS key validation")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL key validation: {e}")
        continue
    b = client.bind(model=model, temperature=0)
    check("plain", lambda: b.invoke([HumanMessage(content="Reply with the word OK")]).content[:60])
    check("json_mode", lambda: client.bind(model=model, temperature=0, response_format={"type": "json_object"})
          .invoke([HumanMessage(content='Return JSON {"ok": true}')]).content[:60])
    check("tool_call", lambda: client.bind_tools(TOOLS, tool_choice="auto").bind(model=model, temperature=0)
          .invoke([HumanMessage(content="Use the add tool for 2+3")]).tool_calls)
