"""Agent tools: Claude tool definitions and the handlers that run them.

Each handler takes the tool input dict the model sent and returns a JSON-ready
dict. Bad input returns {"error": "..."} instead of raising, so the agent loop
can hand the message back to the model and let it retry.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from pydantic import ValidationError

from degree_planner_backend import lookups

logger = logging.getLogger(__name__)

# Fixed text on purpose: the real exception goes to the log, never to the model,
# so database internals (table names, thread ids, file paths) stay out of the chat.
CATALOG_UNAVAILABLE = (
    "The course catalog could not be read. This is a server problem, not a problem with your query: "
    "do not retry with a different query; tell the student the catalog is unavailable right now."
)


def _is_valid_text(value: str) -> bool:
    """False for strings holding lone surrogates (e.g. from a JSON '\\ud800' escape), which SQLite cannot encode."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True

SEARCH_LIMIT_MAX = 50
SEARCH_LIMIT_DEFAULT = 20

SEARCH_CATALOG_TOOL: dict[str, Any] = {
    "name": "search_catalog",
    "description": (
        "Search the Colorado School of Mines course catalog by course code or title. "
        "The match is a case-insensitive substring over the code (for example 'CSCI' or 'MATH201') "
        "and the title (for example 'linear algebra'); descriptions are not searched. "
        "Returns a list of matching courses with code, title, credits, and catalog_year, sorted by code. "
        "An empty list means nothing matched, not an error: try a shorter or different query. "
        "Use get_prerequisites for a course's prerequisites. Only plan with courses this tool returns."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text to find in a course code or title, such as 'CSCI4' or 'thermodynamics'.",
            },
            "catalog_year": {
                "type": "string",
                "description": "Restrict to one catalog year, formatted like '2026-2027'. Omit to search all years.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": SEARCH_LIMIT_MAX,
                "description": f"Maximum number of courses to return (default {SEARCH_LIMIT_DEFAULT}).",
            },
        },
        "required": ["query"],
    },
}


def search_catalog(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {"error": 'tool input must be an object such as {"query": "CSCI"}.'}

    query = tool_input.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "query is required and must be non-empty text, such as 'CSCI' or 'linear algebra'."}
    if not _is_valid_text(query):
        return {"error": "query contains characters that are not valid text; use plain letters and digits."}

    catalog_year = tool_input.get("catalog_year")
    if catalog_year is not None and (not isinstance(catalog_year, str) or not _is_valid_text(catalog_year)):
        return {"error": "catalog_year must be text like '2026-2027', or omitted."}

    limit = tool_input.get("limit", SEARCH_LIMIT_DEFAULT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= SEARCH_LIMIT_MAX:
        return {"error": f"limit must be a whole number from 1 to {SEARCH_LIMIT_MAX}."}

    try:
        courses = lookups.search_catalog(connection, query, catalog_year=catalog_year, limit=limit)
    except sqlite3.Error:
        logger.exception("search_catalog: database error")
        return {"error": CATALOG_UNAVAILABLE}
    except ValidationError:
        logger.exception("search_catalog: a stored course row is malformed")
        return {"error": CATALOG_UNAVAILABLE}
    return {
        "courses": [
            {"code": c.code, "title": c.title, "credits": c.credits, "catalog_year": c.catalog_year}
            for c in courses
        ],
        "count": len(courses),
    }
