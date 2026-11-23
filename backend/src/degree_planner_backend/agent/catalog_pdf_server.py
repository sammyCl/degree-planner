"""MCP server that lets the eval's checker read the Mines catalog PDFs in data/ (read-only).

The live catalog site (catalog.mines.edu) can refuse connections, so the checker (checker.py) also
gets the official PDFs the team collected (the 2026-2027 Undergraduate and Graduate Catalogs, every
program, minor and certificate PDF, the policies and the forms) and the two raw course lists
exported from the catalog (data/Academic Catalog/*.csv), for courses no PDF describes, such as HASS,
PAGN and LIFL. The team's own data (data/json) is never offered, so the checker reads the catalog's
own wording rather than how we turned it into data. (The course CSVs are what courses.json is built
from, so for course facts the checker is less independent than for program rules; it still catches
mistakes in our parsing of them.)

    python -m degree_planner_backend.agent.catalog_pdf_server --root ../data

Tools: list_pdfs, search_pdfs, read_pdf_pages, lookup_courses. Each PDF page is cited as
pdf:<path>#page=<n>, where <path> is relative to the root, for example
pdf:Undergraduate Programs/Computer Science/Computer Science.pdf#page=2; a course row as
csv:<file>#<code>, for example csv:mines-courses.csv#HASS202. Only stderr is used for
logging: stdout carries the MCP messages.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pypdf import PdfReader

logger = logging.getLogger(__name__)

SERVER_NAME = "catalog"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
MAX_PAGES_PER_READ = 5
MAX_RESULTS = 25
SNIPPET = 300
_CITATION = re.compile(r"^pdf:(?P<path>.+\.pdf)#page=(?P<page>[1-9][0-9]*)$")
_COURSE_CITATION = re.compile(r"^csv:(?P<file>[^#/]+\.csv)#(?P<code>[A-Z]{3,4}[0-9]{3}[A-Z]{0,2})$")
COURSE_FILES = ("mines-courses.csv", "mines-graduate-courses.csv")
MAX_CODES = 20

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_pdfs",
        "description": "Lists every Mines catalog PDF you can read: the 2026-2027 Undergraduate and Graduate "
                       "Catalogs (Academic Catalog/), one PDF per bachelor's program (Undergraduate Programs/<dept>/), "
                       "graduate program (Graduate Programs/<dept>/), minor and ASI (Minors and ASIs/), certificate, "
                       "policy and form. Program PDFs hold the degree requirement tables and that department's course "
                       "descriptions (credits, prerequisites, terms offered). Returns path and page count for each.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_pdfs",
        "description": "Finds pages containing the text, ignoring case and spacing (so 'CSCI 370' also finds "
                       "'CSCI370'). Searches every PDF, or only one when path is given. Returns up to 25 matches, each "
                       "with path, page, a snippet, and the citation to use in a finding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "text to find, for example a course code or a phrase"},
                "path": {"type": "string", "description": "optional: one PDF's path from list_pdfs"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_pdf_pages",
        "description": "Returns the text of up to 5 pages of one PDF, with each page's citation. Pages are numbered "
                       "from 1, as in search results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "first_page": {"type": "integer", "minimum": 1},
                "last_page": {"type": "integer", "minimum": 1},
            },
            "required": ["path", "first_page"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_courses",
        "description": "Returns the catalog's own course entries for up to 20 course codes, from the course lists "
                       "exported from the online catalog (undergraduate and graduate): title, credits, description "
                       "(which often gives the terms offered, as (I) fall, (II) spring, (S) summer), prerequisites "
                       "and corequisites, exactly as the catalog wrote them. Use it for any course, especially ones "
                       "no PDF describes (HASS, PAGN, LIFL and other departments without a program PDF). A code may "
                       "have one row in each list. Each row has the citation to use in a finding.",
        "input_schema": {
            "type": "object",
            "properties": {"codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_CODES}},
            "required": ["codes"],
            "additionalProperties": False,
        },
    },
]
TOOL_NAMES = tuple(tool["name"] for tool in TOOL_DEFINITIONS)


def _squash(text: str) -> str:
    """Lowercase with all whitespace removed, for matching that ignores spacing and line breaks."""
    return re.sub(r"\s+", "", text).lower()


def citation(path: str, page: int) -> str:
    return f"pdf:{path}#page={page}"


class PdfLibrary:
    """The PDFs under root, by path relative to root. Text is extracted the first time a file is used."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.paths = sorted(
            str(p.relative_to(self.root)) for p in self.root.rglob("*.pdf")
            if "json" not in p.relative_to(self.root).parts
        )
        self._text: dict[str, list[str]] = {}
        self._courses: dict[tuple[str, str], list[dict[str, str]]] | None = None

    def courses(self) -> dict[tuple[str, str], list[dict[str, str]]]:
        """(file, code) -> the CSV rows for that code, read the first time."""
        if self._courses is None:
            self._courses = {}
            for name in COURSE_FILES:
                path = self.root / "Academic Catalog" / name
                if not path.exists():
                    continue
                with open(path, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        code = row.get("course_number", "").strip()
                        self._courses.setdefault((name, code), []).append(row)
        return self._courses

    def pages(self, path: str) -> list[str]:
        if path not in self.paths:
            raise KeyError(path)
        if path not in self._text:
            reader = PdfReader(self.root / path)
            self._text[path] = [page.extract_text() or "" for page in reader.pages]
        return self._text[path]

    def page_text(self, citation_text: str) -> str | None:
        """The text a citation names (a PDF page, or every row of a course in one CSV), or None."""
        c = _COURSE_CITATION.match(citation_text.strip())
        if c:
            rows = self.courses().get((c["file"], c["code"]))
            if not rows:
                return None
            fields = ("course_number", "course_name", "credits", "description", "prerequisites", "corequisites")
            return "\n".join(" ".join(row.get(k, "") for k in fields) for row in rows)
        m = _CITATION.match(citation_text.strip())
        if not m or m["path"] not in self.paths:
            return None
        pages = self.pages(m["path"])
        number = int(m["page"])
        return pages[number - 1] if number <= len(pages) else None

    def quote_on_page(self, citation_text: str, quote: str) -> bool:
        """True when the quote appears in the cited page or course row, ignoring case and spacing."""
        text = self.page_text(citation_text)
        squashed = _squash(quote)
        return text is not None and bool(squashed) and squashed in _squash(text)

    # ---- the tools

    def call(self, name: str, args: Any) -> dict[str, Any]:
        args = args if isinstance(args, dict) else {}
        try:
            if name == "list_pdfs":
                return {"pdfs": [{"path": p, "pages": len(PdfReader(self.root / p).pages)} for p in self.paths]}
            if name == "search_pdfs":
                return self._search(args)
            if name == "read_pdf_pages":
                return self._read(args)
            if name == "lookup_courses":
                return self._lookup(args)
        except KeyError as exc:
            return {"error": f"no PDF at {exc.args[0]!r}; use a path from list_pdfs."}
        return {"error": f"there is no tool named {name!r}; the tools are {', '.join(TOOL_NAMES)}."}

    def _search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not _squash(query):
            return {"error": "query must be some text to find."}
        path = args.get("path")
        paths = [path] if isinstance(path, str) else self.paths
        want = _squash(query)
        matches = []
        for p in paths:
            for number, text in enumerate(self.pages(p), start=1):
                flat = " ".join(text.split())
                if want in _squash(flat):
                    # Find roughly where it is, for the snippet.
                    first = _squash(query)[:6]
                    at = max(0, _squash_index(flat, first) - SNIPPET // 3)
                    matches.append({"path": p, "page": number, "citation": citation(p, number),
                                    "snippet": flat[at:at + SNIPPET]})
                    if len(matches) >= MAX_RESULTS:
                        return {"matches": matches, "note": f"stopped at {MAX_RESULTS} matches; narrow the query or give a path"}
        return {"matches": matches} if matches else {"matches": [], "note": "no page contains that text"}

    def _lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        codes = args.get("codes")
        if not isinstance(codes, list) or not codes or len(codes) > MAX_CODES:
            return {"error": f"codes must be a list of 1 to {MAX_CODES} course codes."}
        found, missing = [], []
        courses = self.courses()
        for raw in codes:
            code = re.sub(r"\s+", "", str(raw)).upper()
            rows = [(name, row) for name in COURSE_FILES for row in courses.get((name, code), [])]
            if rows:
                found += [_course_entry(name, row) for name, row in rows]
            else:
                missing.append(code)
        result: dict[str, Any] = {"courses": found}
        if missing:
            result["not_found"] = missing
        return result

    def _read(self, args: dict[str, Any]) -> dict[str, Any]:
        path, first = args.get("path"), args.get("first_page")
        last = args.get("last_page", first)
        if not isinstance(path, str):
            return {"error": "path is required."}
        if not (isinstance(first, int) and isinstance(last, int)) or first < 1 or last < first:
            return {"error": "first_page and last_page must be page numbers from 1, with last_page >= first_page."}
        pages = self.pages(path)
        if first > len(pages):
            return {"error": f"{path} has {len(pages)} pages."}
        last = min(last, len(pages), first + MAX_PAGES_PER_READ - 1)
        return {"pages": [{"page": n, "citation": citation(path, n), "text": pages[n - 1]} for n in range(first, last + 1)],
                "page_count": len(pages)}


def _course_entry(name: str, row: dict[str, str]) -> dict[str, str]:
    code = row.get("course_number", "").strip()
    return {
        "citation": f"csv:{name}#{code}",
        "code": code,
        "title": row.get("course_name", ""),
        "credits": row.get("credits", ""),
        "description": row.get("description", ""),
        "prerequisites": row.get("prerequisites", ""),
        "corequisites": row.get("corequisites", ""),
    }


def _squash_index(flat: str, squashed_prefix: str) -> int:
    """Index in flat where the squashed prefix starts (approximately), for snippets."""
    if not squashed_prefix:
        return 0
    lowered = flat.lower()
    for i in range(len(lowered)):
        if _squash(lowered[i:i + len(squashed_prefix) * 2]).startswith(squashed_prefix):
            return i
    return 0


def build_server(library: PdfLibrary) -> Server:
    async def list_tools(_context: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
            for t in TOOL_DEFINITIONS
        ])

    async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        result = library.call(params.name, params.arguments if params.arguments is not None else {})
        return types.CallToolResult(content=[types.TextContent(text=json.dumps(result))], isError="error" in result)

    return Server(SERVER_NAME, on_list_tools=list_tools, on_call_tool=call_tool)


async def _serve(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server with the Mines catalog PDFs, read-only")
    parser.add_argument("--root", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    asyncio.run(_serve(build_server(PdfLibrary(args.root))))


if __name__ == "__main__":
    main()
