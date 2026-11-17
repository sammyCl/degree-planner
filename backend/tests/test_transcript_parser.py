from pathlib import Path

import pytest

from degree_planner_backend import transcript_parser
from degree_planner_backend.transcript_parser import (
    TranscriptParseError,
    parse_transcript_csv,
    parse_transcript_pdf,
)


def test_parse_transcript_csv_reads_regular_transfer_and_apl_rows() -> None:
    text = (
        "code,credits,term,transfer_from\n"
        "MATH111,4.0,transfer,Front Range Community College\n"
        "CSCI191,1.0,aplcredit,\n"
        "CSCI200,4.0,Fall 2024,\n"
    )

    courses = parse_transcript_csv(text)

    assert [c.code for c in courses] == ["MATH111", "CSCI191", "CSCI200"]
    assert courses[0].term == "transfer"
    assert courses[0].transfer_from == "Front Range Community College"
    assert courses[1].term == "aplcredit"
    assert courses[1].transfer_from is None
    assert courses[2].credits == 4.0
    assert courses[2].term == "Fall 2024"


def test_parse_transcript_csv_rejects_missing_columns() -> None:
    with pytest.raises(TranscriptParseError):
        parse_transcript_csv("code,credits\nMATH111,4.0\n")


def test_parse_transcript_csv_rejects_non_numeric_credits() -> None:
    with pytest.raises(TranscriptParseError):
        parse_transcript_csv("code,credits,term\nMATH111,four,transfer\n")


def test_parse_transcript_csv_rejects_blank_required_field() -> None:
    with pytest.raises(TranscriptParseError):
        parse_transcript_csv("code,credits,term\n,4.0,transfer\n")


def test_parse_transcript_lines_handles_semesters_transfer_and_apl() -> None:
    lines = [
        "Transfer Credit",
        "MATH111 Calculus I (Front Range Community College) 4.00",
        "AP Credit",
        "CSCI191 Intro Topics 1.00",
        "Fall 2024",
        "CSCI200 Computer Science I A 4.00",
        "CSCI306 Algorithms B+ 3.00",
        "Spring 2025",
        "CSCI400 Database Management A- 3.00",
    ]

    courses = transcript_parser._parse_transcript_lines(lines)

    assert [(c.code, c.term, c.credits, c.transfer_from) for c in courses] == [
        ("MATH111", "transfer", 4.00, "Front Range Community College"),
        ("CSCI191", "aplcredit", 1.00, None),
        ("CSCI200", "Fall 2024", 4.00, None),
        ("CSCI306", "Fall 2024", 3.00, None),
        ("CSCI400", "Spring 2025", 3.00, None),
    ]


def test_parse_transcript_lines_ignores_lines_before_any_heading() -> None:
    lines = ["Mines Unofficial Transcript", "CSCI200 Computer Science I A 4.00"]

    assert transcript_parser._parse_transcript_lines(lines) == []


def test_parse_transcript_lines_ignores_non_course_lines_within_a_term() -> None:
    lines = ["Fall 2024", "Total Credits: 7.00", "CSCI200 Computer Science I A 4.00"]

    courses = transcript_parser._parse_transcript_lines(lines)

    assert len(courses) == 1
    assert courses[0].code == "CSCI200"


def test_parse_transcript_pdf_extracts_from_each_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdfReader:
        def __init__(self, _path: str) -> None:
            self.pages = [
                FakePage("Fall 2024\nCSCI200 Computer Science I A 4.00"),
                FakePage("Spring 2025\nCSCI306 Algorithms B+ 3.00"),
            ]

    monkeypatch.setattr(transcript_parser, "PdfReader", FakePdfReader)

    courses = parse_transcript_pdf(tmp_path / "transcript.pdf")

    assert [(c.code, c.term, c.credits) for c in courses] == [
        ("CSCI200", "Fall 2024", 4.00),
        ("CSCI306", "Spring 2025", 3.00),
    ]
