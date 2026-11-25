"""Agent tools: Claude tool definitions and the handlers that run them.

Each handler takes the tool input dict the model sent and returns a JSON-ready
dict. Bad input returns {"error": "..."} instead of raising, so the agent loop
can hand the message back to the model and let it retry.
"""

from __future__ import annotations

import functools
import json
import math
import logging
import re
import sqlite3
import unicodedata
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from degree_planner_backend import lookups, validator
from degree_planner_backend.models import CourseRequirement, ExceptionRequirement, Requirement
from degree_planner_backend.plan_models import Flag, Plan, PlannedCourse, Semester, Student, Summary

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
    """Shared wrapper: rejects non-dict input, turns _BadInput into an error, and turns every other
    failure into the fixed CATALOG_UNAVAILABLE message, with the details in the log."""

    def decorate(body: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        @functools.wraps(body)
        def handler(connection: sqlite3.Connection, tool_input: dict[str, Any], *context: Any) -> ToolResult:
            if not isinstance(tool_input, dict):
                return {"error": f"tool input must be a JSON object with the fields in the {tool_name} schema."}
            try:
                return body(connection, tool_input, *context)
            except _BadInput as exc:
                return {"error": str(exc)}
            except sqlite3.Error:
                logger.exception("%s: database error", tool_name)
                return {"error": CATALOG_UNAVAILABLE}
            except ValidationError:
                logger.exception("%s: a stored row is malformed", tool_name)
                return {"error": CATALOG_UNAVAILABLE}
            except Exception:
                # Last resort: a tool must never raise into the agent loop. Anything that gets
                # here is a bug in the tool or the data; it is logged in full for us, and the
                # model gets the same fixed message as for any other server-side failure.
                logger.exception("%s: unexpected error", tool_name)
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
            {"code": c.code, "title": c.title, "credits": c.credits, "catalog_year": _shown_year(c.catalog_year)}
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
        "Returns code, catalog_year, prerequisites, summary, corequisites, and corequisites_summary. "
        "prerequisites and corequisites are each the same kind of tree: {'type': 'course', 'code': ...} is "
        "one course, with an optional min_grade such as 'C-'; {'type': 'exception', 'label': ...} is an "
        "approval such as 'instructor approval', not a course; {'type': 'AND', 'of': [...]} needs all of "
        "its parts; {'type': 'OR', 'of': [...]} needs any one. "
        "prerequisites/corequisites is null and the matching summary is 'none' when the course has none. "
        "Each summary is its tree as one line, such as 'CSCI306 AND (MATH201 OR MATH223)'; "
        "an approval appears as exception: \"instructor approval\" and is never already satisfied, so tell "
        "the student they need it. '(empty OR group)' means the catalog data is broken for that course: "
        "tell the student rather than guessing. "
        "Codes listed as prerequisites or corequisites may be missing from the catalog; "
        "check each with search_catalog before planning with it. "
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
        course_dict: dict[str, Any] = {"type": "course", "code": requirement.code}
        if requirement.min_grade is not None:
            course_dict["min_grade"] = requirement.min_grade
        return course_dict
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
        return requirement.code if requirement.min_grade is None else f"{requirement.code} ({requirement.min_grade} or better)"
    if isinstance(requirement, ExceptionRequirement):
        return f"exception: {json.dumps(clean_label(requirement.label), ensure_ascii=False)}"
    if not requirement.of:
        return f"(empty {requirement.type} group)"
    if len(requirement.of) == 1:
        return summarize_requirement(requirement.of[0], top=top)
    text = f" {requirement.type} ".join(summarize_requirement(part, top=False) for part in requirement.of)
    return text if top else f"({text})"


# Whole quoted list items only ('2025-2026'), so a stored '2025-2026x' is never read as 2025-2026.
_QUOTED_YEAR = re.compile(r"'([0-9]{4}-[0-9]{4})'")


def _years_in(exc: Exception) -> list[str]:
    """The catalog years named in an AmbiguousLookupError message, and nothing else from it.

    The message (from lookups) starts with the id that was looked up, which may itself contain
    something year-shaped ('1999-2000-minor'), so only the text after 'catalog years' is read.
    Replace with a years attribute on the exception once lookups provides one (BUG-023).
    """
    _head, found, tail = str(exc).partition("catalog years")
    return sorted(set(_QUOTED_YEAR.findall(tail))) if found else []


def _shown_year(year: object) -> str:
    """A stored catalog year as the model may see it: only '2026-2027'-shaped text, else a marker."""
    return year if isinstance(year, str) and _CATALOG_YEAR.fullmatch(year) else "(invalid year)"


def _not_in_year_message(
    lookup: Callable[[], Any], *, subject: str, catalog_year: str, unknown_hint: str, tool_name: str
) -> str:
    """Something is not in the catalog year asked for: say whether it exists in other years.

    lookup() repeats the lookup without a catalog year. It is only a hint: if it fails (a malformed
    row in another year, a database error), fall back to the plain not-found message, because the
    thing is still not in the year asked for, and reporting a server outage instead would make the
    model give up on a request that was fine. Only catalog years are added, never the input.
    """
    plain = f"no {subject} in catalog year {catalog_year}. {unknown_hint}"
    try:
        other = lookup()
    except lookups.AmbiguousLookupError as exc:
        # Never suggest the year that was just asked for: that would send the model in a loop.
        years = [year for year in _years_in(exc) if year != catalog_year]
        if not years:
            return plain
        return (
            f"no {subject} in catalog year {catalog_year}; it exists in catalog years {', '.join(years)}. "
            "Call again with one of them as catalog_year."
        )
    except lookups.NotFoundError:
        return plain
    except (sqlite3.Error, ValidationError):
        logger.exception("%s: other-year hint lookup failed", tool_name)
        return plain
    return (
        f"no {subject} in catalog year {catalog_year}; it exists only in catalog year "
        f"{_shown_year(other.catalog_year)}. Call again with that catalog_year or omit it."
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
        return {
            "error": _not_in_year_message(
                lambda: lookups.get_course(connection, code),
                subject=f"course {code}",
                catalog_year=catalog_year,
                unknown_hint="Use search_catalog to find the exact code, or omit catalog_year.",
                tool_name="get_prerequisites",
            )
        }

    prerequisites = course.prerequisites
    corequisites = course.corequisites
    return {
        "code": course.code,
        "catalog_year": _shown_year(course.catalog_year),
        "prerequisites": requirement_to_dict(prerequisites) if prerequisites is not None else None,
        "summary": summarize_requirement(prerequisites),
        "corequisites": requirement_to_dict(corequisites) if corequisites is not None else None,
        "corequisites_summary": summarize_requirement(corequisites),
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
    "(lowercase letters, digits, and hyphens){tail}"
)


def _program_id_field(tool_input: dict[str, Any], *, required: bool, tail: str) -> str | None:
    """A program id slug, at most _PROGRAM_ID_MAX characters, never 'any'. The input is never echoed."""
    message = _PROGRAM_ID_MESSAGE.format(tail=tail)
    program_id = _text_field(tool_input, "program_id", required=required, message=message)
    if program_id is None:
        return None
    if len(program_id) > _PROGRAM_ID_MAX or not _PROGRAM_ID.fullmatch(program_id):
        raise _BadInput(message)
    if program_id == "any":
        raise _BadInput(
            "'any' is not a program id: it only marks forms that apply to every program. Pass a real program id"
            + tail
        )
    return program_id

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


def _program_exists(connection: sqlite3.Connection, program_id: str, tool_name: str = "get_forms") -> bool:
    """True if any catalog year holds the program. A malformed program row still counts as existing:
    the forms are what was asked for, so a broken program row must not hide them."""
    try:
        lookups.get_program(connection, program_id)
    except lookups.NotFoundError:
        return False
    except lookups.AmbiguousLookupError:
        return True
    except ValidationError:
        logger.exception("%s: program row for %s is malformed", tool_name, program_id)
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
    program_id = _program_id_field(tool_input, required=False, tail=", or omit program_id to list every form.")
    program_found = None if program_id is None else _program_exists(connection, program_id)

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


# --- get_program_requirements -------------------------------------------------

PROGRAM_NAME_MAX = 200
SUMMARY_COURSES_SHOWN = 10
WARNING_CODES_SHOWN = 5
PROGRAM_GROUPS_MAX = 60
GROUP_COURSES_MAX = 300
WARNINGS_MAX = 20
COMBINES_MAX = 20
DOUBLE_COUNTS_MAX = 20

GET_PROGRAM_REQUIREMENTS_TOOL: dict[str, Any] = {
    "name": "get_program_requirements",
    "description": (
        "Get what one Colorado School of Mines program (bachelor's, master's, combined BS+MS, minor, or ASI) "
        "requires: name, degree_level, catalog_year, total_credits_required, requirement_groups, combines, "
        "double_counts_with, and data_warnings. "
        "Each requirement group has kind 'all' (take every listed course) or 'choose_credits' (take enough "
        "of the listed courses to reach credits_required), and a one-line summary. "
        "courses null means the data has no course list for that group: read the label to see what counts. "
        "Only a label such as 'Free Electives' means any course; a label such as 'credits approved by the "
        "department' means the student must get the courses approved, so say that instead of choosing them. "
        "A summary ending '(list incomplete, see data_warnings)' had entries left out of the data. "
        "A combined program lists its component programs in combines: call this tool for each of them as "
        "well. If a component returns 'no program with this id', that component's data is not loaded: say "
        "so, the combined program itself still exists. double_counts_with names another program, the "
        "courses that may count toward both, and the most credits that may be shared. "
        "data_warnings lists problems in the stored data: mention them to the student instead of guessing. "
        "Some program rules are not in this data (for example 'at least one elective at the 400 level' or "
        "'not open to students in a given major'), so tell the student to confirm the final plan with "
        "their advisor. program_id must be an id from the loaded program data, such as the one the "
        "student chose; do not guess ids."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "program_id": {
                "type": "string",
                "description": "Program id such as 'computer-science-minor' or 'mining-bs'.",
            },
            "catalog_year": {
                "type": "string",
                "description": "Catalog year formatted like '2026-2027'. Needed only if the program is in several years.",
            },
        },
        "required": ["program_id"],
    },
}

PROGRAM_NOT_FOUND = (
    "no program with this id in the loaded program data. The id may be mistyped, or the program's data "
    "may not be loaded yet: check the id against the program the student chose. Do not guess the "
    "requirements; tell the student they are not available."
)


CREDITS_SHOWN_MAX = 1000


def _format_credits(value: float | None) -> str:
    """Credits as plain text, rounded to 2 decimals, never in scientific notation: 3, 1.5, 120.
    Missing, infinite, NaN, or absurd values show as '?' (never raises)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return "?"
    if abs(value) > CREDITS_SHOWN_MAX:
        return "?"
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


class _Warnings(list):
    """data_warnings with repeats removed and a cap, so broken data cannot flood the reply.
    Pinned warnings (the ones that change whether the program can be planned at all) are listed
    first and are never cut by the cap."""

    def __init__(self) -> None:
        super().__init__()
        self.pinned: list[str] = []

    def add(self, text: str, *, pinned: bool = False) -> None:
        if text in self or text in self.pinned:
            return
        (self.pinned if pinned else self).append(text)

    def capped(self) -> list[str]:
        room = max(WARNINGS_MAX - len(self.pinned), 1)
        if len(self) <= room:
            return self.pinned + list(self)
        return self.pinned + list(self[: room - 1]) + [f"and {len(self) - room + 1} more data warnings"]


def _unusable_credits(value: float | None) -> bool:
    """Missing, not finite, too large to be real, or rounding to zero or less."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return True
    return abs(value) > CREDITS_SHOWN_MAX or round(value, 2) <= 0


def _valid_codes(raw_codes: list[str], where: str, warnings: _Warnings) -> tuple[list[str], bool]:
    """Course codes in order, cleaned up the same way as model input ('CSCI 200' -> 'CSCI200'),
    without repeats. Anything still not course-shaped is left out and reported once.
    Returns (codes, incomplete), where incomplete means something was left out."""
    codes: list[str] = []
    dropped: list[str] = []
    fixed: list[str] = []
    for raw in raw_codes:
        text = raw if isinstance(raw, str) and _is_valid_text(raw) else ""
        visible = "".join(char for char in text if unicodedata.category(char) != "Cf")
        code = _normalize_code(unicodedata.normalize("NFKC", visible).strip())
        if _COURSE_CODE.fullmatch(code):
            if code != text and code not in fixed:
                fixed.append(code)
            if code not in codes:
                codes.append(code)
        else:
            shown = clean_text(str(raw), 20) or "(empty)"
            if shown not in dropped:
                dropped.append(shown)
    if len(codes) > GROUP_COURSES_MAX:
        warnings.add(f"{where}: {len(codes)} courses; only the first {GROUP_COURSES_MAX} are listed")
        codes = codes[:GROUP_COURSES_MAX]
        incomplete = True
    else:
        incomplete = False
    if fixed:
        shown = ", ".join(fixed[:WARNING_CODES_SHOWN])
        more = f" and {len(fixed) - WARNING_CODES_SHOWN} more" if len(fixed) > WARNING_CODES_SHOWN else ""
        warnings.add(f"{where}: stored codes needed cleanup (case, spaces, or hidden characters): {shown}{more}")
    if dropped:
        shown = ", ".join(dropped[:WARNING_CODES_SHOWN])
        more = f" and {len(dropped) - WARNING_CODES_SHOWN} more" if len(dropped) > WARNING_CODES_SHOWN else ""
        warnings.add(f"{where}: left out entries that are not course codes: {shown}{more}")
        incomplete = True
    return codes, incomplete


def _course_list_text(codes: list[str]) -> str:
    if not codes:
        return "(no valid courses listed)"
    shown = ", ".join(codes[:SUMMARY_COURSES_SHOWN])
    if len(codes) > SUMMARY_COURSES_SHOWN:
        shown += f", and {len(codes) - SUMMARY_COURSES_SHOWN} more (see courses)"
    return shown


def summarize_group(
    kind: str, courses: list[str] | None, credits_required: float | None, label: str = "", incomplete: bool = False
) -> str:
    """One line per requirement group, e.g. 'choose 3 credits from: CSCI358, MATH334'.

    With no course list, the label is part of the summary: 'no list' can mean free electives or
    'courses the department approves', and only the label tells which.
    """
    if kind == "all":
        text = f"take all of: {_course_list_text(courses or [])}"
    elif courses is None:
        what = f": {label}" if label else ""
        text = f"choose {_format_credits(credits_required)} credits{what} (no course list in the data)"
    else:
        text = f"choose {_format_credits(credits_required)} credits from: {_course_list_text(courses)}"
    return text + " (list incomplete, see data_warnings)" if incomplete else text


def _group_to_dict(group: Any, warnings: _Warnings) -> dict[str, Any]:
    group_id = clean_text(group.group_id, FORM_ID_MAX) or "(no id)"
    where = f"group {group_id}"
    courses, incomplete = (None, False) if group.courses is None else _valid_codes(group.courses, where, warnings)
    clean_label_text = clean_text(group.label, LABEL_MAX)
    label = clean_label_text or group_id
    credits = group.credits_required
    if courses is None and not clean_label_text:
        warnings.add(f"{where}: no label and no course list, so what counts for it is unknown")
    if group.kind == "all" and not courses:
        warnings.add(f"{where}: kind 'all' with no courses listed")
    if group.kind == "all" and credits is not None:
        warnings.add(f"{where}: kind 'all' also gives credits_required, which is ignored")
    if group.kind == "choose_credits":
        if courses == []:
            warnings.add(f"{where}: choose_credits with an empty course list")
        if _unusable_credits(credits):
            warnings.add(f"{where}: credits_required is missing, zero, negative, or not a usable number")
    return {
        "group_id": group_id,
        "label": label,
        "kind": group.kind,
        "courses": courses,
        "credits_required": credits,
        "summary": summarize_group(group.kind, courses, credits, label, incomplete),
    }


def _program_to_dict(connection: sqlite3.Connection, program: Any) -> ToolResult:
    warnings = _Warnings()
    program_id = clean_text(program.program_id, _PROGRAM_ID_MAX)
    total = program.total_credits_required
    if _unusable_credits(total):
        warnings.add("total_credits_required is missing, zero, negative, or not a usable number")
    year = _shown_year(program.catalog_year)
    if year != program.catalog_year:
        warnings.add("the stored catalog year is not in the form 2026-2027")

    raw_groups = program.requirement_groups
    if len(raw_groups) > PROGRAM_GROUPS_MAX:
        warnings.add(f"{len(raw_groups)} requirement groups; only the first {PROGRAM_GROUPS_MAX} are listed")
    groups = [_group_to_dict(group, warnings) for group in raw_groups[:PROGRAM_GROUPS_MAX]]
    seen_ids: set[str] = set()
    for group in groups:
        if group["group_id"] in seen_ids:
            warnings.add(f"group id {group['group_id']} appears more than once")
        seen_ids.add(group["group_id"])

    combines: list[str] = []
    for raw in program.combines:
        cleaned = clean_text(raw, _PROGRAM_ID_MAX)
        if not _PROGRAM_ID.fullmatch(cleaned):
            warnings.add("combines: left out an entry that is not a program id")
        elif cleaned == program_id:
            warnings.add("combines: the program lists itself; left out")
        elif cleaned not in combines:
            combines.append(cleaned)
    if len(combines) > COMBINES_MAX:
        warnings.add(f"combines: {len(combines)} components; only the first {COMBINES_MAX} are listed")
        combines = combines[:COMBINES_MAX]
    for component in combines:
        if not _program_exists(connection, component, "get_program_requirements"):
            warnings.add(f"combines: component {component} is not in the loaded program data")

    double_counts: list[dict[str, Any]] = []
    raw_shares = program.double_counts_with
    if len(raw_shares) > DOUBLE_COUNTS_MAX:
        warnings.add(f"double_counts_with: {len(raw_shares)} entries; only the first {DOUBLE_COUNTS_MAX} are read")
    for share in raw_shares[:DOUBLE_COUNTS_MAX]:
        other = clean_text(share.program_id, _PROGRAM_ID_MAX)
        if not _PROGRAM_ID.fullmatch(other):
            warnings.add("double_counts_with: left out an entry whose program id is not valid")
            continue
        where = f"double_counts_with {other}"
        shared, _incomplete = _valid_codes(share.shared_courses, where, warnings)
        if any(existing["program_id"] == other for existing in double_counts):
            warnings.add(f"{where}: this program appears more than once, with separate limits; ask the advisor which applies")
        limit = share.shared_credit_limit
        if _unusable_credits(limit):
            warnings.add(f"{where}: shared_credit_limit is missing, zero, negative, or not a usable number")
        elif not _unusable_credits(total) and limit > total:
            warnings.add(f"{where}: shared_credit_limit is larger than the program's total credits")
        double_counts.append({"program_id": other, "shared_courses": shared, "shared_credit_limit": limit})

    result: ToolResult = {
        "program_id": program_id,
        "name": clean_text(program.name, PROGRAM_NAME_MAX) or "(unnamed program)",
        "degree_level": program.degree_level,
        "catalog_year": year,
        "total_credits_required": total,
        "requirement_groups": groups,
        "combines": combines,
        "double_counts_with": double_counts,
        "data_warnings": [],
    }
    if combines:
        own = "has no requirement groups of its own" if not groups else "also has requirements in its components"
        result["note"] = (
            f"This program {own}: call get_program_requirements for each program in combines, and use "
            "their double_counts_with for credits that count toward both."
        )
    elif not groups:
        warnings.add(
            "this program has no requirement groups in the loaded data, so its requirements are unknown: "
            "do not plan against it; tell the student",
            pinned=True,
        )
    result["data_warnings"] = warnings.capped()
    return result


@_tool_handler("get_program_requirements")
def get_program_requirements(connection: sqlite3.Connection, tool_input: dict[str, Any]) -> ToolResult:
    program_id = _program_id_field(tool_input, required=True, tail=".")
    assert program_id is not None
    catalog_year = _catalog_year_field(tool_input)

    try:
        program = lookups.get_program(connection, program_id, catalog_year)
    except lookups.AmbiguousLookupError as exc:
        years = _years_in(exc)
        if not years:
            return {"error": PROGRAM_NOT_FOUND}
        return {
            "error": f"this program is in catalog years {', '.join(years)}. Call again with one of them as catalog_year."
        }
    except lookups.NotFoundError:
        if catalog_year is None:
            return {"error": PROGRAM_NOT_FOUND}
        return {
            "error": _not_in_year_message(
                lambda: lookups.get_program(connection, program_id),
                subject="program with this id",
                catalog_year=catalog_year,
                unknown_hint=PROGRAM_NOT_FOUND[0].upper() + PROGRAM_NOT_FOUND[1:],
                tool_name="get_program_requirements",
            )
        }
    return _program_to_dict(connection, program)


# --- check_plan -----------------------------------------------------------------

# The most semesters any request can ask for (the bachelor's limit). request_models.py reads its
# bachelor's limit from here, so the request format and check_plan never disagree.
SEMESTERS_MAX = 18
COURSES_PER_SEMESTER_MAX = 12
SEMESTER_LABEL_MAX = 40
FLAG_MESSAGE_MAX = 600
COURSE_DESCRIPTION_MAX = 1000
FLAGS_SHOWN_MAX = 30
# Only these flag types may be overridden by the student (docs/plan-format.md, DECISIONS.md).
# Any other override in the record is ignored and logged: it must never hide a real error.
OVERRIDABLE_FLAG_TYPES = frozenset({"exception_claimed"})


@dataclass(frozen=True)
class StudentContext:
    """What the agent loop knows about the student, passed to check_plan by the loop, never by the model.

    overrides holds (flag type, course code or None) pairs the student chose to override in the
    frontend, e.g. ("exception_claimed", "MNGN501"). They are keyed by course code, not course id,
    so an override survives the model moving the course to another semester.
    """

    student: Student
    overrides: frozenset[tuple[str, str | None]] = frozenset()

    def __post_init__(self) -> None:
        # Checked here, when the loop builds the context, so a wiring bug fails loudly in the loop
        # instead of reaching the model as "catalog unavailable".
        if not isinstance(self.student, Student):
            raise TypeError("StudentContext.student must be a plan_models.Student")
        if not isinstance(self.overrides, (set, frozenset)):
            raise TypeError("StudentContext.overrides must be a set of (flag type, course code or None) pairs")
        cleaned = set()
        for item in self.overrides:
            if not (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
                    and (item[1] is None or isinstance(item[1], str))):
                raise ValueError(f"bad override {item!r}: expected (flag type, course code or None)")
            flag_type, code = item
            cleaned.add((flag_type, None if code is None else _clean_stored_code(code)))
        # Codes cleaned up like plan codes, so an override stored as 'mngn 501' matches MNGN501.
        object.__setattr__(self, "overrides", frozenset(cleaned))


def _clean_stored_code(code: str) -> str:
    """A course code from the student's record, cleaned up like model input ('csci 100' -> 'CSCI100').
    Text that cannot be cleaned (lone surrogates) is returned unchanged and simply never matches."""
    if not _is_valid_text(code):
        return code
    return _normalize_code(unicodedata.normalize("NFKC", code).strip())


CHECK_PLAN_TOOL: dict[str, Any] = {
    "name": "check_plan",
    "description": (
        "Check a proposed semester-by-semester plan against the rules: prerequisite order, program "
        "requirements, credit totals, and credits shared between programs. Send only semesters and "
        "course codes; credits and titles come from the catalog, and the student's programs, catalog "
        "year, and completed courses come from their record (you cannot change those). "
        "Returns requirements_met, total_credits, total_credits_required, semesters (label, credits, and "
        "the courses kept), errors, warnings, unknown_courses, and open_exceptions. Each error or warning "
        "has type, course, message, and overridable, plus overridden: true when the student already "
        "overrode it. What to do: broken_prerequisite means move the course later or add "
        "the missing course in an earlier semester; requirement_unmet means add the missing courses; "
        "credit_shortfall means add courses from that group (or any courses, for the total); "
        "double_count_exceeded means fewer shared courses; unknown_course means the code is not in the "
        "catalog for the student's year, so remove it or find the right code with search_catalog, never "
        "keep an invented course; program_not_loaded means that program's requirements could not be "
        "checked, so tell the student; no_programs means the student's record names no program, so tell "
        "the student their programs must be chosen first; transcript_duplicate means the record lists a "
        "completed course twice with different credits and the smaller was used, so ask the student to "
        "check their transcript. "
        "already_completed and duplicate_course warnings mean that course was left out of the plan, so do not "
        "tell the student it is there. A course may appear in more than one semester only when a program "
        "requires it every semester, it is a 0-credit seminar, or it is a PAGN course; any other repeat is "
        "left out. "
        "a final 'more' entry means the list was cut, so fix the ones shown first. "
        "exception_claimed is a warning only the student can override, and open_exceptions lists the "
        "courses whose exception the student has not decided yet: requirements_met can be true while "
        "open_exceptions is not empty, but the plan is not final until you have asked the student about "
        "each one. Never decide an exception for them; if the student says they do not have it, remove "
        "that course or replace it. Call again after every change until "
        "requirements_met is true, or tell the student why it cannot be."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "semesters": {
                "type": "array",
                "minItems": 1,
                "maxItems": SEMESTERS_MAX,
                "description": "Semesters in order, earliest first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Such as 'Fall 2027'."},
                        "courses": {
                            "type": "array",
                            "maxItems": COURSES_PER_SEMESTER_MAX,
                            "items": {"type": "string"},
                            "description": "Course codes such as 'CSCI200'.",
                        },
                    },
                    "required": ["label", "courses"],
                },
            },
        },
        "required": ["semesters"],
    },
}

_SEMESTERS_MESSAGE = (
    f"semesters must be a list of 1 to {SEMESTERS_MAX} objects, each "
    '{"label": "Fall 2027", "courses": ["CSCI200", ...]} with at most '
    f"{COURSES_PER_SEMESTER_MAX} course codes."
)


def _issue(issue_type: str, course: str | None, message: str, overridable: bool = False) -> dict[str, Any]:
    return {"type": issue_type, "course": course, "message": clean_text(message, FLAG_MESSAGE_MAX), "overridable": overridable}


def _capped_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(issues) <= FLAGS_SHOWN_MAX:
        return issues
    rest = len(issues) - FLAGS_SHOWN_MAX + 1
    return issues[: FLAGS_SHOWN_MAX - 1] + [_issue("more", None, f"and {rest} more; fix the ones above first")]


@dataclass
class BuiltPlan:
    """A Plan built from the model's semesters, plus what the tool found while building it.

    plan keeps the student's record exactly as given, for saving as the final plan.
    validation_plan is the same plan with the record cleaned up for checking: transcript codes
    normalized and deduped, programs deduped, and programs that are not loaded left out. Run the
    validator on validation_plan, then save its result with student=plan.student.
    """

    plan: Plan
    validation_plan: Plan
    course_codes: dict[str, str]  # course_id -> code
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    unknown_courses: list[str]
    missing_programs: list[str]


def _parse_semesters(tool_input: dict[str, Any]) -> list[tuple[str, list[str]]]:
    raw = tool_input.get("semesters")
    if not isinstance(raw, list) or not 1 <= len(raw) <= SEMESTERS_MAX:
        raise _BadInput(_SEMESTERS_MESSAGE)
    semesters = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise _BadInput(_SEMESTERS_MESSAGE)
        label_raw = item.get("label")
        label = clean_text(label_raw, SEMESTER_LABEL_MAX) if isinstance(label_raw, str) and _is_valid_text(label_raw) else ""
        courses = item.get("courses")
        if not isinstance(courses, list) or len(courses) > COURSES_PER_SEMESTER_MAX:
            raise _BadInput(_SEMESTERS_MESSAGE)
        codes = []
        for entry in courses:
            if not isinstance(entry, str) or not _is_valid_text(entry):
                raise _BadInput("every course must be a course code such as 'CSCI200'.")
            code = _normalize_code(unicodedata.normalize("NFKC", entry).strip())
            if not _COURSE_CODE.fullmatch(code):
                # Do not echo the input back: it can be long or carry text aimed at the model.
                raise _BadInput(
                    f"semester {index} has an entry that is not a course code such as 'CSCI200' "
                    "(3-4 letters, 3 digits, optional letter suffix). Use search_catalog to find the code."
                )
            codes.append(code)
        semesters.append((label or f"Semester {index}", codes))
    return semesters


# A group label like "required every fall and spring semester" (EENG500 Graduate Seminar).
_EVERY_SEMESTER = re.compile(r"\bevery\s+(?:fall\s+and\s+spring\s+)?semester\b", re.IGNORECASE)


def _every_semester_codes(connection: sqlite3.Connection, program_ids: list[str], year: str) -> set[str]:
    """Courses in a requirement group whose label says it is required every semester, in the
    student's programs and their components. Programs that cannot be found are skipped here; they
    are reported below."""
    codes: set[str] = set()
    pending, seen = list(program_ids), set()
    while pending:
        program_id = pending.pop()
        if program_id in seen:
            continue
        seen.add(program_id)
        try:
            program = lookups.get_program(connection, program_id, year)
        except lookups.NotFoundError:
            continue
        pending += list(program.combines)
        for group in program.requirement_groups:
            if _EVERY_SEMESTER.search(group.label or "") and group.courses:
                codes.update(group.courses)
    return codes


def may_repeat(code: str, credits: float, every_semester: set[str]) -> bool:
    """A course that may be planned in more than one semester: one a program requires every
    semester, a 0-credit seminar or colloquium, or a PAGN physical activity course (BUG-027, BUG-042).
    It still counts once toward a requirement group; each semester's credits count toward the total."""
    return code in every_semester or credits == 0 or code.startswith("PAGN")


def build_plan(connection: sqlite3.Connection, context: StudentContext, semesters: list[tuple[str, list[str]]]) -> BuiltPlan:
    """Turn semesters of course codes into a Plan: catalog titles and credits, generated course ids,
    the student's record, and their overrides. Unknown courses, already-completed courses, and repeats
    are left out and reported. Shared by check_plan and the agent loop (for the final plan)."""
    student = context.student
    year = student.catalog_year
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    unknown: list[str] = []
    # Transcript codes are cleaned up like model input ('csci 100' -> 'CSCI100') and deduped, so a
    # completed course is never counted twice, once from the record and once from the plan.
    # When the record lists a course twice with different credits, the smaller is kept: the larger
    # could let a plan pass that does not have the credits.
    by_code: dict[str, Any] = {}
    for done in student.completed_courses:
        code = _clean_stored_code(done.code)
        earlier = by_code.get(code)
        if earlier is None:
            by_code[code] = done.model_copy(update={"code": code})
            continue
        if earlier.credits != done.credits:
            warnings.append(
                _issue(
                    "transcript_duplicate",
                    code if _COURSE_CODE.fullmatch(code) else None,
                    f"The record lists {code if _COURSE_CODE.fullmatch(code) else 'a completed course'} more than "
                    f"once with different credits; the smaller ({_format_credits(min(earlier.credits, done.credits))}) was used.",
                )
            )
            if done.credits < earlier.credits:
                by_code[code] = done.model_copy(update={"code": code})
    completed_courses = list(by_code.values())
    completed = set(by_code)
    seen: set[str] = set()
    course_codes: dict[str, str] = {}
    plan_semesters: list[Semester] = []
    every_semester = _every_semester_codes(connection, list(dict.fromkeys(student.programs)), year)

    for index, (label, codes) in enumerate(semesters, start=1):
        planned: list[PlannedCourse] = []
        in_this_semester: set[str] = set()
        for code in codes:
            if code in in_this_semester:
                warnings.append(_issue("duplicate_course", code, f"{code} is planned twice in {label}; only one counts."))
                continue
            try:
                course = lookups.get_course(connection, code, year)
            except lookups.NotFoundError:
                course = None
            repeatable = course is not None and may_repeat(code, course.credits, every_semester)
            if code in completed and not repeatable:
                warnings.append(_issue("already_completed", code, f"{code} is already completed; left out of the plan."))
                continue
            if code in seen and not repeatable:
                warnings.append(_issue("duplicate_course", code, f"{code} is planned more than once; only the first counts."))
                continue
            seen.add(code)
            in_this_semester.add(code)
            if course is None:
                unknown.append(code)
                errors.append(_issue("unknown_course", code, f"{code} is not in the {_shown_year(year)} catalog; left out of the plan."))
                continue
            course_id = f"sem-{index}-{code.lower()}"
            course_codes[course_id] = code
            planned.append(
                PlannedCourse(
                    course_id=course_id,
                    code=code,
                    title=clean_text(course.title, PROGRAM_NAME_MAX) or code,
                    credits=course.credits,
                    status="planned",
                    description=clean_text(course.description, COURSE_DESCRIPTION_MAX),
                    corequisites=course.corequisites,
                )
            )
        plan_semesters.append(Semester(semester_id=f"sem-{index}", label=label, courses=planned))

    missing: list[str] = []
    checkable_programs: list[str] = []
    program_errors: list[dict[str, Any]] = []
    if not student.programs:
        program_errors.append(_issue("no_programs", None, "The student's record names no program, so nothing can be checked."))
    for program_id in dict.fromkeys(student.programs):  # deduped, order kept
        shown = clean_text(program_id, _PROGRAM_ID_MAX)
        missing_part: str | None = None
        try:
            program = lookups.get_program(connection, program_id, year)
        except lookups.NotFoundError:
            missing_part = shown
        else:
            for component in program.combines:
                try:
                    lookups.get_program(connection, component, year)
                except lookups.NotFoundError:
                    missing_part = f"{clean_text(component, _PROGRAM_ID_MAX)}, a component of {shown},"
                    break
        if missing_part is not None:
            missing.append(shown)
            program_errors.append(
                _issue(
                    "program_not_loaded",
                    None,
                    f"{missing_part} is not in the loaded {_shown_year(year)} program data, so the requirements "
                    f"of {shown} were not checked. Do not plan against it; tell the student.",
                )
            )
            continue
        checkable_programs.append(program_id)
    errors[:0] = program_errors

    code_to_ids: dict[str, list[str]] = {}
    for course_id, code in course_codes.items():
        code_to_ids.setdefault(code, []).append(course_id)
    override_flags: list[Flag] = []
    for flag_type, code in sorted(context.overrides, key=str):
        if flag_type not in OVERRIDABLE_FLAG_TYPES:
            logger.warning("check_plan: ignored an override of %r, which is not overridable", flag_type)
            continue
        ids = code_to_ids.get(code, []) if code is not None else [None]
        for course_id in ids:
            override_flags.append(
                Flag(flag_id="override", type=flag_type, severity="warning", course_id=course_id,
                     message="", overridable=True, overridden=True)
            )

    plan = Plan(
        student=student,
        semesters=plan_semesters,
        flags=override_flags,
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    validation_plan = plan.model_copy(
        update={"student": student.model_copy(update={"programs": checkable_programs, "completed_courses": completed_courses})}
    )
    return BuiltPlan(plan, validation_plan, course_codes, errors, warnings, unknown, missing)


@_tool_handler("check_plan")
def check_plan(connection: sqlite3.Connection, tool_input: dict[str, Any], context: StudentContext | None = None) -> ToolResult:
    if not isinstance(context, StudentContext):
        # A wiring bug in the agent loop, not something the model can fix.
        logger.error("check_plan called without a StudentContext")
        return {"error": CATALOG_UNAVAILABLE}
    built = build_plan(connection, context, _parse_semesters(tool_input))
    checked = validator.check_plan(connection, built.validation_plan)

    errors = list(built.errors)
    warnings = list(built.warnings)
    for flag in checked.flags:
        course = built.course_codes.get(flag.course_id) if flag.course_id else None
        issue = _issue(flag.type, course, flag.message, flag.overridable)
        if flag.overridden:
            issue["overridden"] = True
            warnings.append(issue)
        elif flag.severity == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    open_exceptions = sorted(
        {built.course_codes[f.course_id] for f in checked.flags
         if f.type == "exception_claimed" and not f.overridden and f.course_id in built.course_codes}
    )
    # Any problem found while building (unknown course, program not loaded, no programs) blocks a pass.
    requirements_met = checked.summary.requirements_met and not built.errors
    return {
        "requirements_met": requirements_met,
        "total_credits": checked.summary.total_credits,
        "total_credits_required": checked.summary.total_credits_required,
        "semesters": [
            {"label": semester.label, "credits": semester.total_credits, "courses": [c.code for c in semester.courses]}
            for semester in checked.semesters
        ],
        "errors": _capped_issues(errors),
        "warnings": _capped_issues(warnings),
        "unknown_courses": built.unknown_courses,
        "open_exceptions": open_exceptions,
    }
