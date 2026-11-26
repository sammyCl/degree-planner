"""Reading a transcript with Claude, for layouts the rule-based reader (transcript_parser.py) does not know.

Called from transfer_credit.read_transcript for every transcript that is not from Mines (and for a Mines one the
rules could not read). Personal details are removed first (redact): lines that name the student, their ID, birth
date, address, phone or email are dropped, and long digit runs, emails and dates of birth inside other lines are
masked. Only the rest of the text is sent, through `claude -p` on the machine's Claude Code login (no API key), with
no tools, and the answer must match TRANSCRIPT_SCHEMA. The answer is then checked again here (codes, credits, terms)
before any row is used; the student reviews every row on the setup page afterwards.

A scanned PDF has no text, so nothing can be removed from it: it is not sent, and the student types the courses in.
The transcript is untrusted content: the system prompt (transcript_reader.md) tells the model to treat it as data,
and the model has no tools, so the worst a hostile transcript can do is produce wrong rows that fail the checks
below or that the student sees and removes.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from degree_planner_backend.agent.agent_file import load_agent
from degree_planner_backend.agent.loop import CLAUDE_COMMAND, ClaudeRun, run_claude
from degree_planner_backend.transcript_parser import TranscriptRow

AGENT = load_agent(Path(__file__).with_name("transcript_reader.md"), available_tools=("none",))
TIMEOUT_SECONDS = 120
# A transcript is a few pages; text far past this is not a transcript, and is not sent rather than cut short.
MAX_CHARACTERS = 60_000

TRANSCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "school": {"type": ["string", "null"]},
        "credit_unit": {"type": "string", "enum": ["semester", "quarter", "unknown"]},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "number": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "credits": {"type": ["number", "null"]},
                    "grade": {"type": ["string", "null"]},
                    "term": {"type": ["string", "null"]},
                    "source": {"type": ["string", "null"]},
                    "in_progress": {"type": "boolean"},
                },
                "required": ["subject", "number", "title", "credits", "grade", "term", "source", "in_progress"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["school", "credit_unit", "rows"],
    "additionalProperties": False,
}


class TranscriptReaderError(RuntimeError):
    """Claude could not read the transcript (not available, timed out, or an answer that does not fit)."""


@dataclass
class ClaudeReading:
    school: str | None
    rows: list[TranscriptRow]
    dropped: list[str] = field(default_factory=list)  # rows in the answer that failed the checks, and why
    cost_usd: float | None = None


# ---------- Removing personal details ----------

# A line that labels personal details: dropped, and when the label stands alone ("Name"), the next line too.
# Strong labels count with or without a colon; place words ("State", "City") only with a colon or alone on the line,
# so "State University of ..." (a school's name) is kept.
_STRONG_LABEL = re.compile(
    r"^\s*(student\s+|legal\s+|full\s+|preferred\s+)?(name|birth\s*date|date\s+of\s+birth|dob|d\.o\.b\.|"
    r"student\s*(id|number|no\.?)|id\s*(number|no\.?)|cwid|banner\s*id|ssn|social\s+security(\s+number)?|"
    r"e-?mail(\s+address)?|phone|telephone|mobile|issued\s+to|prepared\s+for|recipient)(?=\s*[:#]|\s|$)\s*[:#]?",
    re.IGNORECASE,
)
_PLACE_LABEL = re.compile(
    r"^\s*(id|address|mailing\s+address|home\s+address|street|city|state|zip(\s+code)?|postal\s+code)\s*(:|#|$)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# IDs, social security and phone numbers; not credits (they have a decimal point) or years ("2023 - 2024")
_LONG_NUMBER = re.compile(r"(?<![\d.])(\d{3}-\d{2}-\d{4}|\(?\d{3}\)?[ -]?\d{3}-\d{4}|\d{7,})(?![\d.])")
_DATE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[- ](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*([- ]\d{2,4})?)\b",
    re.IGNORECASE,
)
_COURSE_LINE = re.compile(r"^[A-Z]{2,5}\s?\d{3,4}[A-Z]?\b|^[A-Z]{2,5}\s?\dXX\b")


def redact(lines: list[str]) -> tuple[list[str], int]:
    """The transcript's lines without personal details, and how many lines were dropped or masked."""
    kept: list[str] = []
    changed = 0
    skip_next = False
    for raw in lines:
        line = raw.strip()
        if skip_next:
            skip_next = False
            if line and not _COURSE_LINE.match(line):
                changed += 1
                continue
        if not line:
            continue
        label = _STRONG_LABEL.match(line) or _PLACE_LABEL.match(line)
        if label and not _COURSE_LINE.match(line):
            changed += 1
            # "Name" alone on its line: the value is on the next line
            skip_next = len(line[label.end():].strip()) == 0
            continue
        masked = _DATE.sub("[date]", _LONG_NUMBER.sub("[number]", _EMAIL.sub("[email]", line)))
        changed += masked != line
        kept.append(masked)
    return kept, changed


# ---------- Asking Claude ----------

Runner = Callable[[list[str], str, Path], ClaudeRun]


def claude_command() -> list[str]:
    return [
        CLAUDE_COMMAND,
        "-p",
        "--system-prompt", AGENT.system_prompt,
        "--tools", "",  # no tools at all: no files, shell or web
        "--setting-sources", "",  # ignore the machine's Claude Code settings, hooks and plugins
        "--model", AGENT.model,
        "--effort", AGENT.effort,
        "--output-format", "json",
        "--json-schema", json.dumps(TRANSCRIPT_SCHEMA),
        "--no-session-persistence",
    ]


def _default_runner(command: list[str], message: str, cwd: Path) -> ClaudeRun:
    return run_claude(command, message, cwd, timeout=TIMEOUT_SECONDS)


def read_with_claude(lines: list[str], runner: Runner | None = None) -> ClaudeReading:
    """Ask Claude for the course rows of a transcript (already redacted by the caller)."""
    text = "\n".join(lines).strip()
    if not text:
        raise TranscriptReaderError("The file has no text to read (it may be a scanned image).")
    if len(text) > MAX_CHARACTERS:
        raise TranscriptReaderError("The file is much longer than a transcript, so it was not sent to be read.")
    message = f"Read this transcript.\n<transcript>\n{text}\n</transcript>"
    with tempfile.TemporaryDirectory() as work:
        try:
            run = (runner or _default_runner)(claude_command(), message, Path(work))
        except Exception as exc:  # not installed, not signed in, unreadable output
            raise TranscriptReaderError(f"Claude could not be run: {exc}") from exc
    if run.timed_out:
        raise TranscriptReaderError(f"Reading took longer than {TIMEOUT_SECONDS} seconds and was stopped.")
    result = run.result or {}
    answer = result.get("structured_output")
    if result.get("is_error") or not isinstance(answer, dict):
        raise TranscriptReaderError("Claude did not return the transcript's courses.")
    return parse_answer(answer, result.get("total_cost_usd"))


# ---------- Checking the answer ----------

_SUBJECT = re.compile(r"^[A-Z]{2,5}$")
_NUMBER = re.compile(r"^(\d{3,4}[A-Z]{0,2}|\dXX)$")
_SEASON_YEAR = re.compile(r"^(Fall|Spring|Summer|Winter)\s+(\d{4})$", re.IGNORECASE)


def _term(raw: str | None, source: str | None) -> tuple[str, str | None]:
    """The plan format's term (and transfer source): a semester label, "transfer", or "aplcredit"."""
    value = (raw or "").strip().lower()
    if value in ("ap", "aplcredit", "advanced placement"):
        return "aplcredit", None
    if value in ("ib", "international baccalaureate"):
        return "transfer", "IB credit"
    if value == "transfer":
        return "transfer", source
    match = _SEASON_YEAR.match((raw or "").strip())
    if match and 2000 <= int(match.group(2)) <= 2100:
        # Mines has no winter term; a winter quarter elsewhere is shown with the spring that follows it
        season = match.group(1).capitalize()
        return (f"Spring {match.group(2)}" if season == "Winter" else f"{season} {match.group(2)}"), None
    return "transfer", source


def parse_answer(answer: dict[str, Any], cost_usd: Any = None) -> ClaudeReading:
    """Turn Claude's answer into transcript rows, keeping only rows that pass the checks."""
    quarter = answer.get("credit_unit") == "quarter"
    rows: list[TranscriptRow] = []
    dropped: list[str] = []
    for item in answer.get("rows") or []:
        if not isinstance(item, dict):
            continue
        subject = re.sub(r"\s+", "", str(item.get("subject") or "")).upper()
        number = re.sub(r"\s+", "", str(item.get("number") or "")).upper()
        label = f"{subject} {number}".strip() or "a row"
        credits = item.get("credits")
        if not _SUBJECT.match(subject) or not _NUMBER.match(number):
            dropped.append(f"{label}: not a course code")
            continue
        if not isinstance(credits, (int, float)) or isinstance(credits, bool) or not 0 <= credits <= 20:
            dropped.append(f"{label}: no credits shown")
            continue
        if quarter:
            credits = round(credits * 2 / 3, 2)  # quarter hours to semester credits
        term, source = _term(item.get("term"), (item.get("source") or None))
        grade = (str(item["grade"]).strip().upper() or None) if item.get("grade") else None
        title = " ".join(str(item.get("title") or "").split())[:120]
        rows.append(
            TranscriptRow(subject, number, title, grade, float(credits), term, source, bool(item.get("in_progress")) or grade == "IP")
        )
    school = answer.get("school")
    return ClaudeReading(
        school=" ".join(school.split())[:120] if isinstance(school, str) and school.strip() else None,
        rows=rows,
        dropped=dropped,
        cost_usd=cost_usd if isinstance(cost_usd, (int, float)) else None,
    )


def read_redacted(lines: list[str]) -> ClaudeReading:
    """What the transcript reader uses: personal details removed, then read with Claude."""
    kept, _changed = redact(lines)
    return read_with_claude(kept)
