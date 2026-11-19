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
import urllib.parse
from typing import Any, Callable

from pydantic import ValidationError

from degree_planner_backend import lookups
from degree_planner_backend.models import CourseRequirement, ExceptionRequirement, Requirement

logger = logging.getLogger(__name__)

# Fixed text on purpose: the real exception goes to the log, never to the model,
# so database internals (table names, thread ids, file paths) stay out of the chat.
CATALOG_UNAVAILABLE = (
    "The catalog data (courses, programs, forms) could not be read. This is a server problem, not a problem with your request: "
    "do not retry with different input; tell the student the catalog is unavailable right now."
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


def clean_text(text: str, max_len: int) -> str:
    """Scraped text as the model should see it: no invisible or control characters, one line, capped.

    Catalog and form text is scraped, so it is untrusted: format characters (bidi overrides,
    zero-width spaces) are dropped, control characters such as newlines become spaces, runs of
    whitespace collapse, and anything past max_len characters is cut with '...'. May return "".
    """
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        kept.append(" " if category == "Cc" else char)
    cleaned = " ".join("".join(kept).split())
    if len(cleaned) <= max_len:
        return cleaned
    if max_len < 4:
        return cleaned[: max(max_len, 0)]
    cut = max_len - 3
    # Back up so an accent (a combining mark) is not split from the letter it belongs to.
    while cut > 0 and unicodedata.combining(cleaned[cut]):
        cut -= 1
    return cleaned[:cut] + "..."


def clean_label(label: str) -> str:
    """Exception label, cleaned and capped at LABEL_MAX; an empty label shows as '(no label)'."""
    return clean_text(label, LABEL_MAX) or "(no label)"


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


# --- get_forms ----------------------------------------------------------------

FORM_ID_MAX = 100
FORM_NAME_MAX = 200
FORM_REQUIRES_MAX = 500
FORM_NOTES_MAX = 1000
FORM_URL_MAX = 500

# Program ids are lowercase slugs such as 'computer-science-minor' or 'mining-bs-ms-combined'.
_PROGRAM_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_PROGRAM_ID_MAX = 100
_PROGRAM_ID_MESSAGE = (
    "program_id must be a program id such as 'computer-science-minor' "
    "(lowercase letters, digits, and hyphens), or omitted to list every form."
)

GET_FORMS_TOOL: dict[str, Any] = {
    "name": "get_forms",
    "description": (
        "List the Colorado School of Mines registrar forms and catalog policies that apply to a program, "
        "such as independent study credit, transfer course approval, minor declaration, a second "
        "bachelor's degree, or honors programs. Entries whose form_id starts with 'policy-' are policies "
        "(rules to follow), not forms to submit. "
        "Returns forms: a list with form_id, name, applies_to, max_credits, requires, url, and notes. "
        "applies_to lists program ids, and 'any' means every program. "
        "max_credits is a credit cap when the form has one; it is not a degree-wide total unless notes "
        "say so (for independent study it is per course). requires says whose approval or signature is "
        "needed. url is an https link on mines.edu, or null. Read notes before telling the student what to do: they "
        "hold deadlines and limits. Forms are not courses: never put them in the plan as courses. "
        "program_id must be an id from the loaded program data (such as a minor or ASI id the student "
        "chose); do not guess ids or pass 'any' or a subject code. "
        "With program_id, returns that program's forms plus every 'any' form, and program_found. "
        "If program_found is false, the id is mistyped or that program is not loaded yet: the forms "
        "are still listed and note explains what to do. "
        "Without program_id, returns every form."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "program_id": {
                "type": "string",
                "description": "Program id such as 'computer-science-minor'. Omit to list every form.",
            },
        },
        "required": [],
    },
}


def _program_exists(connection: sqlite3.Connection, program_id: str) -> bool:
    """True if any catalog year holds the program. A malformed program row still counts as existing:
    the forms are what was asked for, so a broken program row must not hide them."""
    try:
        lookups.get_program(connection, program_id)
    except lookups.NotFoundError:
        return False
    except lookups.AmbiguousLookupError:
        return True
    except ValidationError:
        logger.exception("get_forms: program row for %s is malformed", program_id)
        return True
    return True


def _optional_text(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    return clean_text(value, max_len) or None


def _safe_url(value: str | None) -> str | None:
    """Only well-formed https links on mines.edu reach the model; anything else becomes None.

    The stored text is checked as it is, never cleaned first: removing a hidden character could
    change where the link points. Too-long URLs are refused rather than cut, since a cut URL is
    a different (broken) link.
    """
    if value is None:
        return None
    url = value.strip()
    if not url or len(url) > FORM_URL_MAX or not url.isascii():
        return None
    if any(unicodedata.category(char) == "Cc" or char in _URL_FORBIDDEN for char in url):
        return None
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or port not in (None, 443):
        return None
    # The whole netloc must be a plain hostname with an optional ":443": no userinfo ('@'),
    # no percent-escapes or ';' in the host, no empty labels ('.mines.edu', 'a..mines.edu').
    if not _URL_NETLOC.fullmatch(parts.netloc.lower()):
        return None
    if host != _URL_DOMAIN and not host.endswith("." + _URL_DOMAIN):
        return None
    return url


_URL_DOMAIN = "mines.edu"
_URL_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_URL_NETLOC = re.compile(rf"{_URL_LABEL}(?:\.{_URL_LABEL})*(?::443)?")
# Characters that have no business in a catalog link and could break out of Markdown or HTML.
_URL_FORBIDDEN = set(' "<>`\\{}|^[]\'')


PROGRAM_NOT_LOADED_NOTE = (
    "This program id is not in the loaded program data. Forms whose applies_to lists this id and forms for "
    "every program are listed, but forms for this program may be missing. Either the id is mistyped or the "
    "program's data is not loaded yet: check the id against the program the student chose before "
    "saying anything to the student about their program."
)


def _form_to_dict(form: Any) -> dict[str, Any]:
    form_id = clean_text(form.form_id, FORM_ID_MAX)
    return {
        "form_id": form_id or "(no id)",
        "name": clean_text(form.name, FORM_NAME_MAX) or form_id or "(unnamed form)",
        # Lowercased so the filter below and the model see the same values ("ANY" -> "any").
        "applies_to": [
            c.lower() for c in (clean_text(unicodedata.normalize("NFKC", a), FORM_ID_MAX) for a in form.applies_to) if c
        ],
        "max_credits": form.max_credits,
        "requires": _optional_text(form.requires, FORM_REQUIRES_MAX),
        "url": _safe_url(form.url),
        "notes": _optional_text(form.notes, FORM_NOTES_MAX),
    }


def _number_duplicate_ids(raw_forms: list[Any]) -> list[dict[str, Any]]:
    """Clean every form, sort by the shown id, and give repeated ids a '#N' suffix.

    Two raw ids can clean to the same text (hidden characters, truncation). The first form with
    an id keeps it; later ones get the lowest '#N' that no other shown id uses (including a real
    id such as 'x#2'), cut so the whole id stays within FORM_ID_MAX. Ties are broken by the raw
    id, so the numbering does not depend on the database's row order.
    """
    pairs = sorted(((_form_to_dict(form), form.form_id) for form in raw_forms), key=lambda p: (p[0]["form_id"], p[1]))
    forms = [form for form, _raw in pairs]
    reserved = {form["form_id"] for form in forms}
    used: set[str] = set()
    for form in forms:
        base = form["form_id"]
        if base in used:
            n = 2
            while True:
                suffix = f"#{n}"
                candidate = base[: FORM_ID_MAX - len(suffix)] + suffix
                if candidate not in used and candidate not in reserved:
                    break
                n += 1
            form["form_id"] = candidate
        used.add(form["form_id"])
    return forms


@_tool_handler("get_forms")
def get_forms(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> ToolResult:
    program_id = _text_field(tool_input, "program_id", required=False, message=_PROGRAM_ID_MESSAGE)
    program_found: bool | None = None
    if program_id is not None:
        if len(program_id) > _PROGRAM_ID_MAX or not _PROGRAM_ID.fullmatch(program_id):
            # Do not echo the input back: it can be very long or carry text aimed at the model.
            raise _BadInput(_PROGRAM_ID_MESSAGE)
        if program_id == "any":
            raise _BadInput(
                "'any' is not a program id: forms for every program are always included. "
                "Pass a real program id, or omit program_id to list every form."
            )
        program_found = _program_exists(connection, program_id)

    # Number the full catalog first, then filter: a form's id must be the same in every call,
    # whatever program_id is, so the model can refer to it later.
    forms = _number_duplicate_ids(lookups.get_forms(connection))
    # Filter on the cleaned values the model is shown, not the raw ones, so a form that reads
    # "applies_to": ["any"] is always in every program's list. Matches are kept even when the
    # program is not loaded (bachelor's programs, for now).
    if program_id is not None:
        forms = [form for form in forms if program_id in form["applies_to"] or "any" in form["applies_to"]]

    result: ToolResult = {"forms": forms, "count": len(forms)}
    if program_found is not None:
        result["program_found"] = program_found
    if program_found is False:
        result["note"] = PROGRAM_NOT_LOADED_NOTE
    return result
