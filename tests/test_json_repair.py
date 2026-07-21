"""Tests for shared/json_repair.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.json_repair import extract_json_array, extract_json_object


def test_extract_object_plain():
    assert extract_json_object('{"score": 90}') == {"score": 90}


def test_extract_object_in_markdown_fence():
    assert extract_json_object('```json\n{"score": 90}\n```') == {"score": 90}


def test_extract_object_repairs_trailing_comma():
    assert extract_json_object('{"score": 90, "ok": true,}') == {"score": 90, "ok": True}


def test_extract_object_returns_empty_on_garbage():
    assert extract_json_object("not json at all") == {}


def test_extract_array_plain():
    assert extract_json_array('[{"q": "a"}]') == [{"q": "a"}]


def test_extract_array_unwraps_object():
    assert extract_json_array('{"faqs": [{"q": "a"}]}') == [{"q": "a"}]


def test_extract_array_repairs_trailing_comma():
    assert extract_json_array('[{"q": "a"},]') == [{"q": "a"}]


def test_extract_array_returns_empty_on_garbage():
    assert extract_json_array("nothing here") == []
