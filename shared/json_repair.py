"""Extract JSON from LLM output, tolerating markdown code fences and trailing
commas. Every app's final-answer parsing needed this same repair pass — it
had been copy-pasted into 5 apps separately (with a drifted bug: one copy
was missing the trailing-comma retry the other four had).
"""
from __future__ import annotations

import json
import re
from typing import Optional, Union


def _try_parse(raw: str) -> Optional[Union[dict, list]]:
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
    except Exception:
        return None


def extract_json_object(content: str) -> dict:
    """Extract a single {...} JSON object from model output. Returns {} on failure."""
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1:
        return {}
    parsed = _try_parse(content[start:end])
    return parsed if isinstance(parsed, dict) else {}


def extract_json_array(content: str) -> list:
    """Extract a JSON array from model output — either a bare [...] array,
    or the first array found inside a wrapping {...} object (e.g.
    {"faqs": [...]})."""
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)

    s = content.find("[")
    parsed = _try_parse(content[s:content.rfind("]") + 1]) if s != -1 else None
    if isinstance(parsed, list):
        return parsed

    s = content.find("{")
    obj = _try_parse(content[s:content.rfind("}") + 1]) if s != -1 else None
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []
