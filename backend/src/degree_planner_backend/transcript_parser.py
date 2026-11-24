"""Transcript parser: turns an uploaded transcript into completed courses
(docs/plan-format.md's `CompletedCourse`), including transfer and AP credit.

Two input formats:

- **CSV**: our own simple format, one row per completed course:
  `code,credits,term,transfer_from`. `term` is `"transfer"`, `"aplcredit"`, or
  a semester label like `"Fall 2024"`. `transfer_from` is the sending
  institution; blank for non-transfer rows.
- **PDF**: the extracted text lists a term heading (a semester label such as
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
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return _parse_transcript_lines(text.splitlines())


def _parse_transcript_lines(lines: list[str]) -> list[CompletedCourse]:
    courses: list[CompletedCourse] = []
    term: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if _TRANSFER_HEADING.search(line):
            term = "transfer"
            continue
        if _APL_HEADING.search(line):
            term = "aplcredit"
            continue
        term_match = _TERM_HEADING.match(line)
        if term_match and int(term_match.group(2)) >= _TERM_YEAR_MIN:
            term = line
            continue

        words = line.split()
        code = words[0] if words else ""
        if term is None or not _COURSE_CODE.match(code):
            continue

        credit_numbers = _CREDITS.findall(line)
        if not credit_numbers:
            continue

        transfer_match = _TRANSFER_FROM.search(line)
        transfer_from = transfer_match.group(1) if (term == "transfer" and transfer_match) else None

        courses.append(
            CompletedCourse(code=code, credits=float(credit_numbers[-1]), term=term, transfer_from=transfer_from)
        )

    return courses
