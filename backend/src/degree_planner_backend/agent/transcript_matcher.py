"""Suggested Mines equivalents for courses from a school with no saved list (option A, 2026-11-26).

For each unmatched course, a shortlist of likely Mines courses is made here from the catalog (title words, with
common short forms; the matching Mines subject; the same level), and Claude picks one code from that shortlist, or a
placeholder (FREE1XX, HASS2XX, CSM2XX, PAGN1XX), or none, with a confidence and a short reason. Only course codes,
titles and credits are sent, never anything about the student. A code that is not in the shortlist is thrown away,
so Claude cannot invent a course. The page pre-fills each suggestion; nothing counts until the student adds it.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from degree_planner_backend.agent.agent_file import load_agent
from degree_planner_backend.agent.loop import CLAUDE_COMMAND, ClaudeRun, run_claude
from degree_planner_backend.agent.transcript_reader import Runner

AGENT = load_agent(Path(__file__).with_name("transcript_matcher.md"), available_tools=("none",))
TIMEOUT_SECONDS = 120
SHORTLIST_SIZE = 14
PLACEHOLDERS = {
    "FREE1XX": "Free elective",
    "HASS2XX": "CAS/HASS mid-level elective",
    "CSM2XX": "Success & Wellness elective",
    "PAGN1XX": "Physical activity",
}

MATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "mines_code": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "mines_code", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class CatalogCourse:
    code: str
    title: str
    credits: float


@dataclass(frozen=True)
class OutsideCourse:
    code: str  # "MATH 1401"
    title: str
    credits: float


@dataclass(frozen=True)
class Suggestion:
    mines_code: str
    title: str
    confidence: str
    reason: str


# ---------- The shortlist, made here without Claude ----------

# Other schools' subjects and the Mines subjects they usually match.
SUBJECTS = {
    "MATH": ["MATH"], "MAT": ["MATH"], "MTH": ["MATH"], "STAT": ["MATH"], "STA": ["MATH"], "APPM": ["MATH"],
    "CSCI": ["CSCI"], "CSC": ["CSCI"], "CS": ["CSCI"], "CSE": ["CSCI"], "CIS": ["CSCI"], "CMPS": ["CSCI"],
    "PHYS": ["PHGN"], "PHY": ["PHGN"], "PHGN": ["PHGN"],
    "CHEM": ["CHGN"], "CHE": ["CHGN"], "CHM": ["CHGN"],
    "BIOL": ["CBEN"], "BIO": ["CBEN"],
    "ECON": ["EBGN"], "ECO": ["EBGN"],
    "GEOL": ["GEGN", "GEOL"], "GEY": ["GEGN", "GEOL"],
    "ENGR": ["EDNS", "CEEN", "MEGN"], "EGG": ["EDNS", "CEEN", "MEGN"], "ENES": ["EDNS", "CEEN", "MEGN"],
    "ELEC": ["EENG"], "EE": ["EENG"], "ECE": ["EENG"], "MECH": ["MEGN"], "ME": ["MEGN"], "CVEN": ["CEEN"],
    "ENGL": ["HASS"], "ENG": ["HASS"], "PHIL": ["HASS"], "PHI": ["HASS"], "HIST": ["HASS"], "HIS": ["HASS"],
    "PSCI": ["HASS"], "POLS": ["HASS"], "PSC": ["HASS"], "SOC": ["HASS"], "ANTH": ["HASS"], "PSY": ["HASS"],
}
_SHORT_FORMS = {
    "calc": "calculus", "intro": "introduction", "prog": "programming", "comp": "computer", "computing": "computer",
    "eng": "engineering", "engr": "engineering", "chem": "chemistry", "phys": "physics", "stats": "statistics",
    "stat": "statistics", "prob": "probability", "diff": "differential", "eqns": "equations", "eq": "equations",
    "org": "organic", "gen": "general", "fund": "fundamentals", "fundamental": "fundamentals", "sci": "science",
    "mech": "mechanics", "elec": "electrical", "struct": "structures", "data": "data", "alg": "algorithms",
    "algo": "algorithms", "lin": "linear", "1": "i", "2": "ii", "3": "iii", "one": "i", "two": "ii", "three": "iii",
}
_STOP = {"and", "of", "the", "for", "in", "to", "a", "an", "with", "w", "lab", "laboratory"}


def _words(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {_SHORT_FORMS.get(w, w)[:7] for w in words if w not in _STOP}


def _level(number: str) -> int:
    """1 for a first-year course (100 or 1000 level), 2 for second-year, and so on."""
    digits = re.match(r"\d+", number)
    return int(digits.group()[0]) if digits else 0


LAB_PAIRS_PATH = Path(__file__).resolve().parents[4] / "data" / "json" / "lab-pairs.json"


@cache
def _lab_pairs() -> dict[str, str]:
    """Mines lab code -> its lecture (data/json/lab-pairs.json, built by data/tools/build_lab_pairs.py)."""
    return json.loads(LAB_PAIRS_PATH.read_text())["pairs"] if LAB_PAIRS_PATH.exists() else {}


def with_lab_pairs(catalog: list[CatalogCourse]) -> list[CatalogCourse]:
    """The catalog plus each Mines lecture and its lab as one choice ("CHGN221+CHGN223"), for an outside course taken
    with its lab."""
    by_code = {c.code: c for c in catalog}
    pairs = []
    for lab, lecture in _lab_pairs().items():
        if lab in by_code and lecture in by_code:
            a, b = by_code[lecture], by_code[lab]
            pairs.append(CatalogCourse(f"{a.code}+{b.code}", f"{a.title} with {b.title}", a.credits + b.credits))
    return catalog + pairs


def shortlist(course: OutsideCourse, catalog: list[CatalogCourse]) -> list[CatalogCourse]:
    """The Mines courses this course most likely matches: shared title words, the usual Mines subject, the same level.
    A course taken with its lab ("CHEM 2031 + CHEM 2038") prefers a Mines lecture with its lab, and a course without
    one does not get those."""
    has_lab = "+" in course.code
    subject, _, rest = course.code.partition(" ")
    number = rest.split(" ")[0]
    subjects = SUBJECTS.get(subject, [subject])
    level = _level(number)
    words = _words(course.title)
    scored: list[tuple[float, CatalogCourse]] = []
    labs_only = set(_lab_pairs())
    for mines in catalog:
        if mines.code in labs_only:
            continue  # a Mines lab is only ever suggested together with its lecture ("CHGN221+CHGN223")
        m_subject = re.match(r"[A-Z]+", mines.code).group()  # type: ignore[union-attr]
        m_level = _level(mines.code[len(m_subject):])
        if m_level > 4:
            continue  # graduate courses are not suggested for transfer credit
        shared = len(words & _words(mines.title))
        score = shared * 3 + (4 if m_subject in subjects else 0) + (2 if m_level == level else 0) - abs(m_level - level) * 0.5
        if "+" in mines.code:
            score += 3 if has_lab else -6
        if shared or m_subject in subjects:
            scored.append((score, mines))
    scored.sort(key=lambda pair: (-pair[0], pair[1].code))
    return [mines for _, mines in scored[:SHORTLIST_SIZE]]


# ---------- Asking Claude to pick ----------


def claude_command() -> list[str]:
    return [
        CLAUDE_COMMAND, "-p",
        "--system-prompt", AGENT.system_prompt,
        "--tools", "",
        "--setting-sources", "",
        "--model", AGENT.model,
        "--effort", AGENT.effort,
        "--output-format", "json",
        "--json-schema", json.dumps(MATCH_SCHEMA),
        "--no-session-persistence",
    ]


def _default_runner(command: list[str], message: str, cwd: Path) -> ClaudeRun:
    return run_claude(command, message, cwd, timeout=TIMEOUT_SECONDS)


def suggest(
    courses: list[OutsideCourse], school: str | None, catalog: list[CatalogCourse], runner: Runner | None = None
) -> list[Suggestion | None]:
    """A suggestion (or None) for each course, in order. Raises on any failure; the caller then shows none."""
    if not courses:
        return []
    full = with_lab_pairs(catalog)
    lists = [shortlist(c, full) for c in courses]
    entries = []
    for index, (course, options) in enumerate(zip(courses, lists)):
        entries.append({
            "index": index,
            "course": f"{course.code} {course.title}".strip(),
            "credits": course.credits,
            "shortlist": [f"{m.code} {m.title}" for m in options] + [f"{code} {name}" for code, name in PLACEHOLDERS.items()],
        })
    message = (
        f"School: {school or 'not known'}\n<courses>\n{json.dumps(entries, ensure_ascii=False, indent=1)}\n</courses>"
    )
    with tempfile.TemporaryDirectory() as work:
        run = (runner or _default_runner)(claude_command(), message, Path(work))
    if run.timed_out:
        raise RuntimeError("suggesting took too long")
    answer = (run.result or {}).get("structured_output")
    if (run.result or {}).get("is_error") or not isinstance(answer, dict):
        raise RuntimeError("Claude returned no suggestions")
    out: list[Suggestion | None] = [None] * len(courses)
    for item in answer.get("suggestions") or []:
        index, code = item.get("index"), item.get("mines_code")
        if not isinstance(index, int) or not 0 <= index < len(courses) or not isinstance(code, str):
            continue
        allowed = {m.code: m.title for m in lists[index]} | PLACEHOLDERS
        if code not in allowed:
            continue  # not from the shortlist: thrown away, never shown
        confidence = item.get("confidence") if item.get("confidence") in ("high", "medium", "low") else "low"
        out[index] = Suggestion(code, allowed[code], confidence, " ".join(str(item.get("reason") or "").split())[:200])
    return out
