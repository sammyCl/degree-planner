"""Agent tools: Claude tool definitions and the handlers that run them.

Each handler takes the tool input dict the model sent and returns a JSON-ready
dict. Bad input returns {"error": "..."} instead of raising, so the agent loop
can hand the message back to the model and let it retry.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import sqlite3
import unicodedata
from typing import Any, Callable

from pydantic import ValidationError

from degree_planner_backend import lookups
from degree_planner_backend.models import CourseRequirement, ExceptionRequirement, Requirement

logger = logging.getLogger(__name__)

# Fixed text on purpose: the real exception goes to the log, never to the model,
# so database internals (table names, thread ids, file paths) stay out of the chat.
CATALOG_UNAVAILABLE = (
    "The course catalog could not be read. This is a server problem, not a problem with your query: "
    "do not retry with a different query; tell the student the catalog is unavailable right now."
)

ToolResult = dict[str, Any]


class _BadInput(Exception):
    """Raised inside a handler for input the model should fix; becomes {"error": message}."""


def _is_valid_text(value: str) -> bool:
    """False for strings holding lone surrogates (e.g. from a JSON '\\ud800' escape), which SQLite cannot encode."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _text_field(tool_input: dict[str, Any], name: str, *, required: bool, message: str) -> str | None:
    """Return a stripped, NFKC-normalized, non-empty string field, None if optional and absent, or raise _BadInput.

    NFKC folds compatibility forms into plain ones (full-width '２０２６' -> '2026', 'ſ' -> 's'),
    so look-alike characters either become the ASCII they look like or stay non-ASCII and fail the checks.
    """
    value = tool_input.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _BadInput(message)
    if not _is_valid_text(value):
        raise _BadInput(f"{name} contains characters that are not valid text; use plain letters and digits.")
    return unicodedata.normalize("NFKC", value).strip()


# Real Mines codes: 3-4 letters, 3 digits, optional 1-2 letter suffix (CSCI400, CSM101, PHGN100LA).
# Placeholders in the raw CSVs such as CSCI1XX or BIOLADD deliberately do not match.
# [0-9] rather than \d: \d also matches non-ASCII digits such as Arabic-Indic '٤'.
_COURSE_CODE = re.compile(r"[A-Z]{3,4}[0-9]{3}[A-Z]{0,2}")
_CATALOG_YEAR = re.compile(r"[0-9]{4}-[0-9]{4}")


def _normalize_code(code: str) -> str:
    """'math 201', 'Math-201', ' MATH201 ' -> 'MATH201'.

    Only ASCII is uppercased: str.upper() maps some non-ASCII letters to ASCII
    (dotless 'ı' -> 'I'), which would let a look-alike code match a real course.
    Non-ASCII codes are returned as they are and then fail _COURSE_CODE.
    """
    code = re.sub(r"[\s\-]+", "", code)
    return code.upper() if code.isascii() else code


def _catalog_year_field(tool_input: dict[str, Any]) -> str | None:
    """Optional catalog_year: None if absent, else text in the form '2026-2027'."""
    year = _text_field(tool_input, "catalog_year", required=False, message=_CATALOG_YEAR_MESSAGE)
    if year is not None and not _CATALOG_YEAR.fullmatch(year):
        raise _BadInput(_CATALOG_YEAR_MESSAGE)
    return year


def _tool_handler(tool_name: str) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    """Shared wrapper: rejects non-dict input, turns _BadInput into an error, and hides database failures."""

    def decorate(body: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        @functools.wraps(body)
        def handler(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> ToolResult:
            if not isinstance(tool_input, dict):
                return {"error": f"tool input must be a JSON object with the fields in the {tool_name} schema."}
            try:
                return body(connection, tool_input)
            except _BadInput as exc:
                return {"error": str(exc)}
            except sqlite3.Error:
                logger.exception("%s: database error", tool_name)
                return {"error": CATALOG_UNAVAILABLE}
            except ValidationError:
                logger.exception("%s: a stored row is malformed", tool_name)
                return {"error": CATALOG_UNAVAILABLE}

        return handler

    return decorate


_CATALOG_YEAR_MESSAGE = "catalog_year must be text like '2026-2027', or omitted."


# --- search_catalog -----------------------------------------------------------

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


@_tool_handler("search_catalog")
def search_catalog(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> ToolResult:
    query = _text_field(
        tool_input,
        "query",
        required=True,
        message="query is required and must be non-empty text, such as 'CSCI' or 'linear algebra'.",
    )
    catalog_year = _catalog_year_field(tool_input)

    limit = tool_input.get("limit", SEARCH_LIMIT_DEFAULT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= SEARCH_LIMIT_MAX:
        raise _BadInput(f"limit must be a whole number from 1 to {SEARCH_LIMIT_MAX}.")

    courses = lookups.search_catalog(connection, query, catalog_year=catalog_year, limit=limit)
    return {
        "courses": [
            {"code": c.code, "title": c.title, "credits": c.credits, "catalog_year": c.catalog_year}
            for c in courses
        ],
        "count": len(courses),
    }


# --- get_prerequisites --------------------------------------------------------

GET_PREREQUISITES_TOOL: dict[str, Any] = {
    "name": "get_prerequisites",
    "description": (
        "Get what a student must complete before taking one Colorado School of Mines course, "
        "and the corequisites they must take in the same semester (or earlier). "
        "Returns code, catalog_year, prerequisites, summary, and corequisites. "
        "prerequisites is a tree: {'type': 'course', 'code': ...} is one course; "
        "{'type': 'exception', 'label': ...} is an approval such as 'instructor approval', not a course; "
        "{'type': 'AND', 'of': [...]} needs all of its parts; {'type': 'OR', 'of': [...]} needs any one. "
        "prerequisites is null and summary is 'none' when the course has no prerequisites. "
        "summary is the same tree as one line, such as 'CSCI306 AND (MATH201 OR MATH223)'; "
        "an approval appears as exception: \"instructor approval\" and is never already satisfied, so tell "
        "the student they need it. '(empty OR group)' means the catalog data is broken for that course: "
        "tell the student rather than guessing. "
        "Codes listed as prerequisites may be missing from the catalog, and corequisites may be free text "
        "rather than course codes; check each with search_catalog before planning with it. "
        "If the course is in several catalog years, the error lists them: "
        "call again with catalog_year set to one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Course code such as 'CSCI400'. Case, spaces, and hyphens are ignored.",
            },
            "catalog_year": {
                "type": "string",
                "description": "Catalog year formatted like '2026-2027'. Needed only if the course is in several years.",
            },
        },
        "required": ["code"],
    },
}


LABEL_MAX = 200


def clean_label(label: str) -> str:
    """Exception label as the model should see it: no invisible or control characters, one line, capped.

    Labels come from scraped catalog text, so they are untrusted: format characters (bidi overrides,
    zero-width spaces) are dropped, control characters such as newlines become spaces, runs of
    whitespace collapse, and anything past LABEL_MAX characters is cut with '...'.
    """
    kept = []
    for char in label:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        kept.append(" " if category == "Cc" else char)
    text = " ".join("".join(kept).split())
    if not text:
        return "(no label)"
    return text if len(text) <= LABEL_MAX else text[: LABEL_MAX - 3] + "..."


def requirement_to_dict(requirement: Requirement) -> dict[str, Any]:
    """The requirement tree as JSON-ready dicts, with every exception label cleaned."""
    if isinstance(requirement, CourseRequirement):
        return {"type": "course", "code": requirement.code}
    if isinstance(requirement, ExceptionRequirement):
        return {"type": "exception", "label": clean_label(requirement.label)}
    return {"type": requirement.type, "of": [requirement_to_dict(part) for part in requirement.of]}


def summarize_requirement(requirement: Requirement | None, *, top: bool = True) -> str:
    """One-line form of a requirement tree, with parentheses around nested AND/OR groups.

    Exception labels are quoted so text like "B AND C" inside a label cannot read as logic.
    A group with one part is shown as that part. An empty group is malformed data and is
    shown as "(empty OR group)" rather than "none", which would wrongly mean "no requirement".
    """
    if requirement is None:
        return "none"
    if isinstance(requirement, CourseRequirement):
        return requirement.code
    if isinstance(requirement, ExceptionRequirement):
        return f"exception: {json.dumps(clean_label(requirement.label), ensure_ascii=False)}"
    if not requirement.of:
        return f"(empty {requirement.type} group)"
    if len(requirement.of) == 1:
        return summarize_requirement(requirement.of[0], top=top)
    text = f" {requirement.type} ".join(summarize_requirement(part, top=False) for part in requirement.of)
    return text if top else f"({text})"


def _not_in_year_message(connection: sqlite3.Connection, code: str, catalog_year: str) -> str:
    """The code is not in that year: say whether it exists in other years, so the model fixes the right thing.

    This second lookup is only a hint. If it fails (a malformed row in another year, a database
    error), fall back to the plain not-found message: the course is still not in the year asked for,
    and reporting a server outage instead would make the model give up on a request that was fine.
    """
    plain = (
        f"no course {code} in catalog year {catalog_year}. "
        "Use search_catalog to find the exact code, or omit catalog_year."
    )
    try:
        other = lookups.get_course(connection, code)
    except lookups.AmbiguousLookupError as exc:
        return f"no course {code} in catalog year {catalog_year}; {exc}."
    except lookups.NotFoundError:
        return plain
    except (sqlite3.Error, ValidationError):
        logger.exception("get_prerequisites: other-year hint lookup failed for %s", code)
        return plain
    return (
        f"no course {code} in catalog year {catalog_year}; {code} exists only in catalog year "
        f"{other.catalog_year}. Call again with that catalog_year or omit it."
    )


@_tool_handler("get_prerequisites")
def get_prerequisites(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> ToolResult:
    raw_code = _text_field(
        tool_input, "code", required=True, message="code is required and must be a course code such as 'CSCI400'."
    )
    code = _normalize_code(raw_code)
    if not _COURSE_CODE.fullmatch(code):
        # Do not echo the input back: it can be very long or carry text aimed at the model.
        raise _BadInput(
            "code must be one course code such as 'CSCI400' (3-4 letters, 3 digits, optional letter suffix). "
            "Use search_catalog to find the exact code."
        )
    catalog_year = _catalog_year_field(tool_input)

    try:
        course = lookups.get_course(connection, code, catalog_year)
    except lookups.AmbiguousLookupError as exc:
        # The lookup's message names the years and says to pass catalog_year; it holds no internals.
        return {"error": f"{exc}."}
    except lookups.NotFoundError:
        if catalog_year is None:
            return {"error": f"no course {code} in the catalog. Use search_catalog to find the exact code."}
        return {"error": _not_in_year_message(connection, code, catalog_year)}

    prerequisites = course.prerequisites
    return {
        "code": course.code,
        "catalog_year": course.catalog_year,
        "prerequisites": requirement_to_dict(prerequisites) if prerequisites is not None else None,
        "summary": summarize_requirement(prerequisites),
        "corequisites": list(course.corequisites),
    }
