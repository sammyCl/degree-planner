"""MCP server that lets the eval's checker read the Mines catalog PDFs in data/ (read-only).

The live catalog site (catalog.mines.edu) can refuse connections, so the checker (checker.py) also
gets the official PDFs the team collected: the 2026-2027 Undergraduate and Graduate Catalogs, every
program, minor and certificate PDF, the policies and the forms. Only PDF files are offered; the
team's own data (data/json) and the course CSVs are not, so the checker stays independent of how
we turned those sources into data.

    python -m degree_planner_backend.agent.catalog_pdf_server --root ../data

Tools: list_pdfs, search_pdfs, read_pdf_pages. Each page is cited as pdf:<path>#page=<n>, where
<path> is relative to the root, for example
pdf:Undergraduate Programs/Computer Science/Computer Science.pdf#page=2. Only stderr is used for
logging: stdout carries the MCP messages.
"""

from __future__ import annotations

import argparse
import asyncio
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

    def pages(self, path: str) -> list[str]:
        if path not in self.paths:
            raise KeyError(path)
        if path not in self._text:
            reader = PdfReader(self.root / path)
            self._text[path] = [page.extract_text() or "" for page in reader.pages]
        return self._text[path]

    def page_text(self, citation_text: str) -> str | None:
        """The text of the page a citation names, or None if it names no real page."""
        m = _CITATION.match(citation_text.strip())
        if not m or m["path"] not in self.paths:
            return None
        pages = self.pages(m["path"])
        number = int(m["page"])
        return pages[number - 1] if number <= len(pages) else None

    def quote_on_page(self, citation_text: str, quote: str) -> bool:
        """True when the quote appears on the cited page, ignoring case and spacing."""
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
