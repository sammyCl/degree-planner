"""Tests for agent/catalog_pdf_server.py, the checker's read-only catalog PDF tools (agent/eval: Samantha).
They read the real PDFs in data/."""

from __future__ import annotations

import pytest

from degree_planner_backend.agent.catalog_pdf_server import DATA_DIR, MAX_PAGES_PER_READ, TOOL_NAMES, PdfLibrary

CS = "Undergraduate Programs/Computer Science/Computer Science.pdf"


@pytest.fixture(scope="module")
def library() -> PdfLibrary:
    return PdfLibrary(DATA_DIR)


def test_only_pdfs_are_offered_and_never_our_json(library: PdfLibrary) -> None:
    assert CS in library.paths
    assert "Academic Catalog/2026-2027 Undergraduate Catalog.pdf" in library.paths
    assert all(p.endswith(".pdf") for p in library.paths)
    assert not any(p.startswith("json") for p in library.paths)


def test_list_pdfs(library: PdfLibrary) -> None:
    listed = library.call("list_pdfs", {})["pdfs"]
    assert {"path": CS, "pages": 17} in listed


def test_search_ignores_case_and_spacing(library: PdfLibrary) -> None:
    for query in ("CSCI370", "csci 370", "Advanced  Software\nEngineering"):
        matches = library.call("search_pdfs", {"query": query, "path": CS})["matches"]
        assert any(m["page"] == 2 and m["citation"] == f"pdf:{CS}#page=2" for m in matches), query


def test_search_everything_is_capped(library: PdfLibrary) -> None:
    result = library.call("search_pdfs", {"query": "MATH"})
    assert len(result["matches"]) == 25 and "stopped at 25" in result["note"]


def test_read_pages_is_capped_at_five(library: PdfLibrary) -> None:
    result = library.call("read_pdf_pages", {"path": CS, "first_page": 1, "last_page": 17})
    assert [p["page"] for p in result["pages"]] == list(range(1, MAX_PAGES_PER_READ + 1))
    assert result["page_count"] == 17
    assert "CSCI370" in result["pages"][1]["text"].replace(" ", "")


@pytest.mark.parametrize("name, args, message", [
    ("read_pdf_pages", {"path": "json/courses.json", "first_page": 1}, "no PDF at"),
    ("read_pdf_pages", {"path": "../backend/degree_planner.db", "first_page": 1}, "no PDF at"),
    ("read_pdf_pages", {"path": CS, "first_page": 99}, "has 17 pages"),
    ("read_pdf_pages", {"path": CS, "first_page": 3, "last_page": 2}, "last_page >= first_page"),
    ("search_pdfs", {"query": "   "}, "some text"),
    ("search_pdfs", {"query": "x", "path": "nope.pdf"}, "no PDF at"),
    ("write_file", {}, "no tool named"),
])
def test_bad_calls_are_errors(library: PdfLibrary, name: str, args: dict, message: str) -> None:
    assert message in library.call(name, args)["error"]


def test_quote_on_page(library: PdfLibrary) -> None:
    cite = f"pdf:{CS}#page=2"
    assert library.quote_on_page(cite, "csci370 advanced  software engineering")
    assert not library.quote_on_page(cite, "offered only in the spring")
    assert not library.quote_on_page(cite, "")
    assert not library.quote_on_page(f"pdf:{CS}#page=0", "CSCI370")


def test_tool_names() -> None:
    assert TOOL_NAMES == ("list_pdfs", "search_pdfs", "read_pdf_pages")
