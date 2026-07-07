"""Tests for shared PDF utilities and safe execution."""
from __future__ import annotations

import numpy as np
import pytest

from shared.pdf_utils import chunk_pages, cosine_similarity, embed_chunks, extract_pages, retrieve
from shared.safe_exec import run_sandboxed_python


def test_extract_pages_returns_text(text_pdf):
    pdf_bytes = text_pdf("This is a test PDF.\nIt has two lines.")
    pages = extract_pages(pdf_bytes)
    assert len(pages) == 1
    assert "test PDF" in pages[0][1]


def test_extract_pages_rejects_scanned_pdf():
    # A PDF with no extractable text should be rejected.
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    with pytest.raises(ValueError, match="scanned/image PDF"):
        extract_pages(buffer.getvalue())


def test_chunk_pages_tagged_with_page_numbers(text_pdf):
    pdf_bytes = text_pdf("Line one. " * 200)
    pages = extract_pages(pdf_bytes)
    chunks = chunk_pages(pages, source="test.pdf")
    assert len(chunks) > 0
    assert all(c.page == 1 for c in chunks)
    assert all(c.source == "test.pdf" for c in chunks)


def test_cosine_similarity():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    c = np.array([1.0, 1.0])
    assert cosine_similarity(a, c) == pytest.approx(0.7071, abs=1e-4)


def test_retrieve_top_k(text_pdf):
    pdf_bytes = text_pdf(
        "Apples are red. Bananas are yellow. "
        "Apples grow on trees. Bananas grow in clusters. "
        "Oranges are orange."
    )
    pages = extract_pages(pdf_bytes)
    chunks = embed_chunks(chunk_pages(pages))
    results = retrieve("apple", chunks, top_k=3)
    assert len(results) <= 3
    assert results[0].score > 0.1


def test_safe_exec_allows_basic_math():
    code = "print(2 + 3 * 4)"
    assert run_sandboxed_python(code) == "14"


def test_safe_exec_forbids_imports():
    code = "import os\nprint(os.getcwd())"
    result = run_sandboxed_python(code)
    assert result.startswith("ERROR:")
    assert "Forbidden syntax: Import" in result or "Imports are not allowed" in result


def test_safe_exec_forbids_file_access():
    code = "print(open('test.pdf').read())"
    result = run_sandboxed_python(code)
    assert result.startswith("ERROR:")


def test_safe_exec_forbids_dunder_tricks():
    code = "print(().__class__.__bases__[0].__subclasses__())"
    result = run_sandboxed_python(code)
    assert result.startswith("ERROR:")


def test_safe_exec_forbids_format_string_escape():
    # .format() does attribute/index traversal inside a string literal,
    # bypassing an AST walk that only looks for real Attribute nodes.
    code = "print('{0.__class__.__bases__}'.format(1))"
    result = run_sandboxed_python(code)
    assert result.startswith("ERROR:")
