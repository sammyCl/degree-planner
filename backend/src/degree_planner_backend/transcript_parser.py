"""Transcript parser: turns an uploaded transcript into completed courses
(docs/plan-format.md's `CompletedCourse`), including transfer and AP credit.

Two input formats:

- **CSV**: our own simple format, one row per completed course:
  `code,credits,term,transfer_from`. `term` is `"transfer"`, `"aplcredit"`, or
  a semester label like `"Fall 2024"`. `transfer_from` is the sending
  institution; blank for non-transfer rows.
- **PDF**: the real Mines unofficial transcript (see "Reading course rows" below), or the extracted text lists a term heading (a semester label such as
  `"Fall 2024"`, or a line containing "Transfer Credit" or "AP Credit") and
  then one line per course: a catalog course code, then anything, then the
  credits (always written with a decimal point, e.g. `4.00`) as the last such
  number on the line. A transfer line may name the institution in
  parentheses, e.g. `"MATH111 Calculus I (Front Range Community College) 4.00"`.

Real transcripts are a student's private data and must never be committed to
this repo; only synthetic samples belong in tests.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from pypdf import PdfReader

from degree_planner_backend.plan_models import CompletedCourse

_COURSE_CODE = re.compile(r"^[A-Z]{2,5}\d{3}[A-Z]?$")
_CREDITS = re.compile(r"\d+\.\d+")
_TRANSFER_FROM = re.compile(r"\(([^)]+)\)")
_TRANSFER_HEADING = re.compile(r"transfer credit", re.IGNORECASE)
_APL_HEADING = re.compile(r"\b(ap|advanced placement)\s*credit\b", re.IGNORECASE)
# BUG-033: [0-9] instead of \d, which also matches other scripts' digits (e.g. full-width "２０２４").
_TERM_HEADING = re.compile(r"^(Fall|Spring|Summer)\s+([0-9]{4})$", re.IGNORECASE)
# The agent request format's start_term floor (request_models.py's START_YEAR_MIN): a transcript
# heading outside a sensible range (e.g. "SUMMER 0001") is not a real term, just text that happens
# to match the shape.
_TERM_YEAR_MIN = 2000

_CSV_REQUIRED_COLUMNS = {"code", "credits", "term"}


class TranscriptParseError(ValueError):
    """A row or line in the transcript could not be read as a completed course."""


def parse_transcript_csv(text: str) -> list[CompletedCourse]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _CSV_REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise TranscriptParseError(f"CSV must have columns {sorted(_CSV_REQUIRED_COLUMNS)} (and optionally transfer_from)")

    courses: list[CompletedCourse] = []
    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        code = (row.get("code") or "").strip()
        credits_raw = (row.get("credits") or "").strip()
        term = (row.get("term") or "").strip()
        transfer_from = (row.get("transfer_from") or "").strip() or None

        if not code or not credits_raw or not term:
            raise TranscriptParseError(f"row {row_number}: code, credits, and term are required")
        try:
            credits = float(credits_raw)
        except ValueError as exc:
            raise TranscriptParseError(f"row {row_number}: credits {credits_raw!r} is not a number") from exc

        courses.append(CompletedCourse(code=code, credits=credits, term=term, transfer_from=transfer_from))
    return courses


def parse_transcript_pdf(path: Path) -> list[CompletedCourse]:
    return _parse_transcript_lines(pdf_lines(path))


def pdf_lines(path: Path) -> list[str]:
    """The text of every page of a PDF, as lines."""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return text.splitlines()


def _parse_transcript_lines(lines: list[str]) -> list[CompletedCourse]:
    """Every course row, read as Mines courses (a Mines transcript already names the Mines course for transfer
    credit). Rows with no credit earned (F, W, ...) are left out."""
    return [row.as_completed() for row in read_rows(lines) if row.earns_credit()]


# ---------- Reading course rows ----------
# Handles both our simple layout (module docstring) and the real Mines unofficial transcript (examples made up):
#   TRANSFER CREDIT ACCEPTED BY INSTITUTION        -> transfer credit follows
#   SP20: IB Credit / 201980: AP Credit            -> where it came from: IB, AP, or a school's name
#   FA19-SP21: Example State University
#   MATH 111 CALC FOR SCI & ENGRS I T 4.000        -> code with a space, title, grade, credits
#   FREE 1XX Free Elective: Example Course T 3.000 -> placeholder credit, numbered FREE1XX-1, FREE1XX-2, ...
#   INSTITUTION CREDIT / Term: Spring 2024         -> Mines semesters
#   CSCI 101 Main / Campus / UG EXAMPLE TITLE A 3.000 12.000
#                                                  -> one row wrapped over lines; credits, then quality points
#   COURSE(S) IN PROGRESS / Term: Fall 2024        -> in progress (counted as completed, marked)
# Another school's transcript is read the same way (subject, number, title, grade, credits); its codes are its own,
# so read_transcript() matches them to Mines courses instead.

_ROW_START = re.compile(r"^([A-Z]{2,5})\s?(\d{3,4}[A-Z]?|\dXX)(?=\s|$)\s*(.*)$")
_SOURCE_HEADING = re.compile(r"^(?:[A-Z]{2}\d{2}(?:\s*-\s*[A-Z]{2}\d{2})?|\d{6}):\s*(.+)$")
_TERM_LABEL = re.compile(r"^(?:Term:\s*)?(Fall|Spring|Summer)\s+([0-9]{4})$", re.IGNORECASE)
_IN_PROGRESS_HEADING = re.compile(r"^COURSE\(?S\)?\s+IN\s+PROGRESS", re.IGNORECASE)
_INSTITUTION_HEADING = re.compile(r"^INSTITUTION CREDIT$", re.IGNORECASE)
_IB_SOURCE = re.compile(r"\b(IB|international baccalaureate)\b", re.IGNORECASE)
# Lines that end a row and say nothing about a course (totals, column headers, standing).
_NOT_A_ROW = re.compile(
    r"^(Term Totals|Attempt Hours|Current Term|Cumulative|Subject\b|Student Type|Academic Standing|"
    r"TRANSCRIPT TOTALS|Transcript Totals|Total |Overall|\(Undergraduate\)|\(Graduate\)|Hours$|Quality|Points$|R$)",
    re.IGNORECASE,
)
_LEVEL_OR_CAMPUS = {"MAIN", "CAMPUS", "UG", "GR"}
# PDF text has typographic ligatures ("Proﬁciency"). Only these are replaced: a full NFKC would also turn full-width
# digits into ASCII, which BUG-033 deliberately rejects.
_LIGATURES = str.maketrans({"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"})
# A lone "I" (incomplete) is not read as a grade: it is far more often the end of a title ("Calculus I 4.00").
_GRADE = re.compile(r"^(A|A-|B\+|B|B-|C\+|C|C-|D\+|D|D-|F|T|W|WI|WF|WP|IP|INC|U|S|P|NC|CR|PRG|Z)$")
# Grades that earn no credit at all.
_NO_CREDIT = {"F", "W", "WI", "WF", "WP", "INC", "U", "NC", "Z"}


class TranscriptRow:
    """One course row as the transcript wrote it, before deciding which Mines course it is."""

    def __init__(self, subject: str, number: str, title: str, grade: str | None, credits: float, term: str,
                 source: str | None, in_progress: bool) -> None:
        self.subject, self.number, self.title, self.grade = subject, number, title, grade
        self.credits, self.term, self.source, self.in_progress = credits, term, source, in_progress
        self.code = f"{subject}{number}"

    @property
    def is_placeholder(self) -> bool:
        return self.number.endswith("XX")

    def earns_credit(self) -> bool:
        return self.grade not in _NO_CREDIT

    def as_completed(self, code: str | None = None, title: str | None = None, credits: float | None = None) -> CompletedCourse:
        return CompletedCourse(
            code=code or self.code,
            credits=self.credits if credits is None else credits,
            term=self.term,
            transfer_from=self.source if self.term == "transfer" else None,
            title=title if title is not None else (self.title or None),
            in_progress=self.in_progress,
        )


def read_rows(lines: list[str]) -> list[TranscriptRow]:
    rows: list[TranscriptRow] = []
    term: str | None = None
    source: str | None = None
    in_progress = False
    buffer: list[str] = []
    buffer_term: tuple[str, str | None, bool] | None = None

    def flush() -> None:
        nonlocal buffer, buffer_term
        if buffer and buffer_term:
            row = _read_row(" ".join(buffer), *buffer_term)
            if row is not None:
                rows.append(row)
        buffer, buffer_term = [], None

    for raw_line in lines:
        line = " ".join(raw_line.translate(_LIGATURES).split())
        if not line:
            continue
        heading = True
        if _TRANSFER_HEADING.search(line):
            term, source = "transfer", None
        elif _APL_HEADING.search(line) and not _ROW_START.match(line):
            term, source = "aplcredit", None
        elif _IN_PROGRESS_HEADING.match(line):
            in_progress = True
        elif _INSTITUTION_HEADING.match(line):
            term, source = None, None
        elif (m := _TERM_LABEL.match(line)) and int(m.group(2)) >= _TERM_YEAR_MIN:
            term, source = f"{m.group(1).capitalize()} {m.group(2)}", None
        elif (m := _SOURCE_HEADING.match(line)) and term in ("transfer", "aplcredit"):
            name = m.group(1).strip()
            if _APL_HEADING.search(name):
                term, source = "aplcredit", None
            elif _IB_SOURCE.search(name):
                term, source = "transfer", "IB credit"
            else:
                term, source = "transfer", name
        else:
            heading = False
        if heading:
            flush()
            continue
        if _ROW_START.match(line):
            flush()
            if term is not None:
                buffer, buffer_term = [line], (term, source, in_progress)
            continue
        if _NOT_A_ROW.match(line):
            flush()
            continue
        if buffer:
            buffer.append(line)  # a row that wrapped onto the next line
            if _CREDITS.search(line):
                flush()
    flush()
    return number_placeholders(rows)


def number_placeholders(rows: list[TranscriptRow]) -> list[TranscriptRow]:
    """Placeholder credit gets a number per row ("FREE1XX-1", "FREE1XX-2"), so each row stays its own course."""
    count: dict[str, int] = {}
    for row in rows:
        if row.is_placeholder:
            base = f"{row.subject}{row.number}"
            count[base] = count.get(base, 0) + 1
            row.code = f"{base}-{count[base]}"
    return rows


def _read_row(text: str, term: str, source: str | None, in_progress: bool) -> TranscriptRow | None:
    match = _ROW_START.match(text)
    if not match:
        return None
    subject, number, rest = match.groups()
    tokens = rest.split()
    first_number = next((i for i, t in enumerate(tokens) if _CREDITS.fullmatch(t)), None)
    if first_number is None:
        return None
    credits = float(tokens[first_number])  # the first number is the credits; a Mines row adds quality points after
    before = tokens[:first_number]
    while before and before[0].upper() in _LEVEL_OR_CAMPUS:
        before = before[1:]
    grade = before.pop() if before and _GRADE.match(before[-1]) else None
    title = " ".join(before)
    if term == "transfer" and source is None and (m := _TRANSFER_FROM.search(title)):
        source = m.group(1)  # our simple layout: "MATH111 Calculus I (Front Range Community College) 4.00"
        title = _TRANSFER_FROM.sub("", title).strip()
    return TranscriptRow(subject, number, title, grade, credits, term, source, in_progress or grade == "IP")
