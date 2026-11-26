"""Reading a transcript for the setup page: which school it is from, and which Mines course each row counts as.

- A Mines transcript already names the Mines course for every transfer course (Mines evaluated them), so its rows
  are taken as they are.
- A transcript from a Colorado Community College System (CCCS) college is matched against Mines' preapproved list
  (data/json/transfer-equivalencies.json, built by data/tools/build_transfer_equivalencies.py). A course not on the
  list is returned as unmatched, suggested as a free elective (the registrar's rule for academic CCCS courses).
- A transcript from any other school: every row is returned as unmatched, for the student to look up in Mines'
  Transfer Evaluation System (TES) and pick the Mines course by hand. Nothing here contacts TES or any other site.

Transfer credit needs a C or better (registrar's general transfer rules); lower grades are listed as skipped.
Real transcripts are private: never commit one; tests use synthetic rows only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from degree_planner_backend.plan_models import CompletedCourse
from degree_planner_backend.transcript_parser import TranscriptRow, number_placeholders, read_rows

EQUIVALENCIES_PATH = Path(__file__).resolve().parents[3] / "data" / "json" / "transfer-equivalencies.json"
MINES = "Colorado School of Mines"
# Grades that transfer: C or better, or a pass. Anything else (C-, D, F, W, ...) does not.
_TRANSFERS = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "P", "S", "CR", "T"}
_SCHOOL_WORDS = re.compile(r"\b(University|College|Institute|School|Academy)\b", re.IGNORECASE)


class UnmatchedCourse(BaseModel):
    """A course from another school with no Mines equivalent found: the student picks one (or skips it)."""

    code: str  # as the other school writes it, e.g. "MATH 1401"
    title: str
    credits: float
    term: str
    in_progress: bool = False
    # the Mines course to offer first, e.g. "FREE1XX" for an unlisted academic CCCS course; null when unknown
    suggestion: str | None = None
    reason: str
    # about the suggestion: the Mines title, who made it ("rule": the registrar's free-elective rule for CCCS
    # colleges; "claude": a guess from the course title, to confirm in TES), how sure, and why
    suggestion_title: str | None = None
    suggested_by: Literal["rule", "claude"] | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    suggestion_reason: str | None = None


class TranscriptReading(BaseModel):
    """What the setup page shows after a transcript is read."""

    school: str | None  # null when the page could not tell; the student then names it
    from_mines: bool
    system: str | None = None  # "Colorado Community College System" when the school shares that numbering
    courses: list[CompletedCourse] = Field(default_factory=list)
    unmatched: list[UnmatchedCourse] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # rows that earn no Mines credit, with the reason
    tes_url: str
    # Mines and every school with a saved list, for the page to offer when it could not tell the school
    known_schools: list[str] = Field(default_factory=list)
    # "rules" (read on this machine) or "claude" (read by Claude after personal details were removed)
    read_by: Literal["rules", "claude"] = "rules"
    # something the student should know about how the file was read, or null
    notice: str | None = None


class ClaudeRows(Protocol):
    """What the Claude reader returns (agent/transcript_reader.py's ClaudeReading)."""

    school: str | None
    rows: list[TranscriptRow]
    dropped: list[str]


# Reads a transcript's lines with Claude (removing personal details first); raises when it cannot.
ClaudeReader = Callable[[list[str]], ClaudeRows]


class SuggestionLike(Protocol):
    mines_code: str
    title: str
    confidence: str
    reason: str


# Suggests a Mines course for each unmatched course (code, title, credits) from a school; raises when it cannot.
Suggester = Callable[[list[UnmatchedCourse], str | None], list[SuggestionLike | None]]


@cache
def load_equivalencies(path: Path = EQUIVALENCIES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


def known_schools(data: dict[str, Any]) -> list[tuple[str, str | None]]:
    """(school, saved list id or None) for every school the reader recognises, Mines first."""
    return [(school["name"], school["system"]) for school in data["schools"]]


def _normal(text: str) -> str:
    """Lowercase words only: "University Of Colorado-Denver" and "university of colorado denver" read the same."""
    text = text.lower().replace("&", " and ").replace("+", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _known_name(name: str, data: dict[str, Any]) -> str | None:
    """The school `name` refers to, written as the school's own name: "CU Denver" and "University Of Colorado-Denver"
    are both "University of Colorado Denver". The longest name or alias that fits wins, so "Colorado State University
    Pueblo" is not taken for "Colorado State University"."""
    padded = f" {_normal(name)} "
    best: tuple[int, str] | None = None
    for school in data["schools"]:
        for candidate in [school["name"], *school["aliases"]]:
            words = _normal(candidate)
            if words and f" {words} " in padded and (best is None or len(words) > best[0]):
                best = (len(words), school["name"])
    return best[1] if best else None


def detect_school(lines: list[str], data: dict[str, Any]) -> str | None:
    """The school a transcript is from: the highest line near the top that names a school the reader knows (Mines
    only in the first few lines, since a transcript from elsewhere may mention Mines lower down), else the first line
    that looks like a school's name, else None."""
    top = [" ".join(line.split()) for line in lines[:20] if line.strip()]
    for index, line in enumerate(top):
        known = _known_name(line, data)
        if known and (known != MINES or index < 6):
            return known
    return next((line for line in top[:6] if _SCHOOL_WORDS.search(line) and len(line) <= 80), None)


def read_transcript(
    lines: list[str],
    school: str | None = None,
    credits_of: Callable[[str], float | None] = lambda _code: None,
    data: dict[str, Any] | None = None,
    claude: ClaudeReader | None = None,
    suggest: Suggester | None = None,
) -> TranscriptReading:
    """Read a transcript's lines. `school` overrides the detected school (the student said which it is).
    `credits_of` gives a Mines course's catalog credits, to split one outside course that becomes two Mines courses.
    `claude` reads layouts the rules do not know: used for any transcript that is not from Mines, and for a Mines one
    the rules found almost nothing in. When it fails, what the rules found is kept and the reading says why.
    `suggest` proposes a Mines course for every course left unmatched (a guess the student confirms in TES)."""
    data = data or load_equivalencies()
    named = (school or "").strip()
    school = named or detect_school(lines, data)
    rows = read_rows(lines)
    reading = TranscriptReading(
        school=school,
        from_mines=school == MINES,
        tes_url=data["tes_url"],
        known_schools=[MINES] + sorted(name for name, _ in known_schools(data) if name != MINES),
    )
    if not any(line.strip() for line in lines):
        reading.notice = "This PDF has no text in it (it looks like a scanned image), so it could not be read. Add your courses by hand, or download a text PDF from your school's student portal."
        return reading
    if claude is not None and not (reading.from_mines and len(rows) >= 3):
        try:
            answer = claude(lines)
        except Exception as exc:  # the reader raises TranscriptReaderError; anything else is treated the same
            reading.notice = f"Claude could not read this transcript ({exc}). Showing what the built-in reader found; check it carefully."
        else:
            rows = number_placeholders(answer.rows)
            reading.read_by = "claude"
            reading.skipped.extend(f"{d} (left out)" for d in answer.dropped)
            if not named and answer.school:
                school = _known_name(answer.school, data) or answer.school
                reading.school, reading.from_mines = school, school == MINES

    if reading.from_mines:
        for row in rows:
            if row.source and row.source != "IB credit":
                row.source = _known_name(row.source, data) or row.source  # "University Of Colorado-Denver"
            if row.earns_credit():
                reading.courses.append(row.as_completed())
            else:
                reading.skipped.append(f"{row.subject} {row.number} {row.title}: grade {row.grade}, no credit")
        return reading

    canonical = _known_name(school, data) if school else None
    system_id = next((sid for name, sid in known_schools(data) if name == canonical and sid), None)
    if canonical:
        school = canonical
    system = data["systems"].get(system_id) if system_id else None
    reading.system = system["name"] if system else None
    entries = [e for e in data["equivalencies"] if e["system"] == system_id] if system_id else []
    used: set[str] = set()
    placeholders: dict[str, int] = {}
    present = {(r.subject, r.number) for r in rows}

    for row in rows:
        label = f"{row.subject} {row.number}"
        if row.grade is not None and row.grade not in _TRANSFERS and not row.in_progress:
            reading.skipped.append(f"{label} {row.title}: grade {row.grade}; Mines needs a C or better to transfer")
            continue
        term = "transfer"
        if not system:
            reading.unmatched.append(_unmatched(row, label, None, "Look this course up in TES to find its Mines equivalent."))
            continue
        mines = _match(row, entries, school or "", used, present)
        if mines is None:
            reading.unmatched.append(
                _unmatched(row, label, "FREE1XX", "Not on Mines' preapproved list. An academic course usually transfers as a free elective; check TES.")
            )
            continue
        for code, credits in _split(mines, row.credits, credits_of):
            if code.endswith("XX"):
                placeholders[code] = placeholders.get(code, 0) + 1
                code = f"{code}-{placeholders[code]}"
            else:
                used.add(code)
            reading.courses.append(
                CompletedCourse(code=code, credits=credits, term=term, transfer_from=school, title=f"{label} {row.title}".strip(), in_progress=row.in_progress)
            )
    if suggest is not None and reading.unmatched:
        _add_suggestions(reading, suggest, school)
    return reading


def _add_suggestions(reading: TranscriptReading, suggest: Suggester, school: str | None) -> None:
    """Claude's guesses replace the plain free-elective suggestion where it found something better; when it fails,
    the courses keep whatever they had and the student looks them up in TES."""
    try:
        guesses = suggest(reading.unmatched, school)
    except Exception:  # noqa: BLE001 - suggestions are a convenience; the list still works without them
        if not reading.notice:
            reading.notice = "Suggested Mines courses could not be made this time. Look the courses up in TES."
        return
    for course, guess in zip(reading.unmatched, guesses):
        if guess is None:
            if course.suggestion:
                course.suggested_by = "rule"
            continue
        course.suggestion = guess.mines_code
        course.suggestion_title = guess.title
        course.suggested_by = "claude"
        course.confidence = guess.confidence  # type: ignore[assignment]
        course.suggestion_reason = guess.reason or None


def _unmatched(row: TranscriptRow, label: str, suggestion: str | None, reason: str) -> UnmatchedCourse:
    return UnmatchedCourse(
        code=label, title=row.title, credits=row.credits, term="transfer", in_progress=row.in_progress,
        suggestion=suggestion, reason=reason,
        suggestion_title="Free elective" if suggestion == "FREE1XX" else None,
        suggested_by="rule" if suggestion else None,
    )


def _match(row: TranscriptRow, entries: list[dict[str, Any]], school: str, used: set[str], present: set[tuple[str, str]]) -> list[str] | None:
    """The Mines courses a row becomes, or None. A Mines course already used falls through to the next entry (the
    second of ECO 2001 and 2002 is a CAS/HASS elective, not a second EBGN201)."""
    for e in entries:
        if row.subject not in e["subjects"] or not (e["any_number"] or row.number in e["numbers"]):
            continue
        if e["only_at"] and school not in e["only_at"]:
            continue
        if e["pair"]:
            partners = [p for p in entries if p["pair"] == e["pair"] and p is not e]
            has_partner = any((s, n) in present for p in partners for s in p["subjects"] for n in p["numbers"])
            if not has_partner or e["pair"] in used:
                return ["FREE1XX"]  # one of the two alone, or the second of the pair: free elective hours
        if all(code in used for code in e["mines"] if not code.endswith("XX")) and not any(code.endswith("XX") for code in e["mines"]):
            continue
        return list(e["mines"])
    return None


def _split(mines: list[str], credits: float, credits_of: Callable[[str], float | None]) -> list[tuple[str, float]]:
    """One outside course that becomes several Mines courses (a lecture and its lab) splits its credits by the Mines
    catalog; without catalog credits, evenly."""
    if len(mines) == 1:
        return [(mines[0], credits)]
    catalog = [credits_of(code) for code in mines]
    if all(c is not None for c in catalog) and sum(catalog) > 0:  # type: ignore[arg-type]
        total = sum(catalog)  # type: ignore[arg-type]
        return [(code, round(credits * c / total, 2)) for code, c in zip(mines, catalog)]  # type: ignore[operator]
    return [(code, round(credits / len(mines), 2)) for code in mines]
