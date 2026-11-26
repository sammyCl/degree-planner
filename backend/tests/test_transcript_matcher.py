"""Suggested Mines equivalents (agent/transcript_matcher.py). No test calls Claude; course rows are made up."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from degree_planner_backend.agent.loop import ClaudeRun
from degree_planner_backend.agent.transcript_matcher import CatalogCourse, OutsideCourse, Suggestion, shortlist, suggest
from degree_planner_backend.transfer_credit import read_transcript

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = [
    CatalogCourse(c["code"], c["title"], c["credits"])
    for c in json.loads((REPO_ROOT / "data" / "json" / "courses.json").read_text())["courses"]
]


@pytest.mark.parametrize(
    "code, title, expected",
    [
        ("MATH 1401", "Calculus I", "MATH111"),
        ("CSCI 1410", "Fundamentals of Computing", "CSCI128"),
        ("CSCI 2312", "Intermediate Programming", "CSCI200"),
        ("MATH 3191", "Applied Linear Algebra", "MATH332"),
        ("ECON 2012", "Principles of Economics: Macroeconomics", "EBGN201"),
        ("PHYS 2311", "General Physics I", "PHGN100"),
    ],
)
def test_the_shortlist_holds_the_likely_mines_course(code: str, title: str, expected: str) -> None:
    codes = [m.code for m in shortlist(OutsideCourse(code, title, 4), CATALOG)]
    assert expected in codes and len(codes) <= 14
    assert not any(c.startswith(("MATH5", "CSCI5", "MATH6", "CSCI6")) for c in codes)  # no graduate courses


def test_suggest_keeps_only_codes_from_each_shortlist() -> None:
    seen: dict[str, str] = {}

    def runner(_command: list[str], message: str, _cwd: Path) -> ClaudeRun:
        seen["message"] = message
        return ClaudeRun(result={"structured_output": {"suggestions": [
            {"index": 0, "mines_code": "MATH111", "confidence": "high", "reason": "Both are first-semester calculus."},
            {"index": 1, "mines_code": "MADE999", "confidence": "high", "reason": "invented"},
            {"index": 2, "mines_code": "FREE1XX", "confidence": "medium", "reason": "No Mines match."},
            {"index": 7, "mines_code": "MATH111", "confidence": "high", "reason": "no such course"},
        ]}})

    courses = [OutsideCourse("MATH 1401", "Calculus I", 4), OutsideCourse("ART 1000", "Drawing", 3), OutsideCourse("PSYC 1000", "Intro Psychology", 3)]
    out = suggest(courses, "University of Colorado Denver", CATALOG, runner)
    assert out[0] == Suggestion("MATH111", "Calculus for Scientists and Engineers I", "high", "Both are first-semester calculus.")
    assert out[1] is None  # a code outside the shortlist is thrown away
    assert out[2] == Suggestion("FREE1XX", "Free elective", "medium", "No Mines match.")
    assert "<courses>" in seen["message"] and "University of Colorado Denver" in seen["message"]


def test_suggest_raises_when_claude_answers_nothing() -> None:
    with pytest.raises(RuntimeError):
        suggest([OutsideCourse("MATH 1401", "Calculus I", 4)], None, CATALOG, lambda *_: ClaudeRun(result={"is_error": True}))


LINES = ["University of Colorado Denver", "Fall 2022", "MATH 1401 Calculus I A 4.000", "ART 1000 Drawing A 3.000"]


def test_read_transcript_pre_fills_suggestions_for_unmatched_courses() -> None:
    def fake(courses, school):  # type: ignore[no-untyped-def]
        assert school == "University of Colorado Denver" and [c.code for c in courses] == ["MATH 1401", "ART 1000"]
        return [Suggestion("MATH111", "Calculus for Scientists and Engineers I", "high", "Both are calculus."), None]

    reading = read_transcript(LINES, suggest=fake)
    first, second = reading.unmatched
    assert (first.suggestion, first.suggested_by, first.confidence, first.suggestion_title) == (
        "MATH111", "claude", "high", "Calculus for Scientists and Engineers I")
    assert second.suggestion is None and second.suggested_by is None
    assert reading.courses == []  # nothing counts until the student adds it


def test_when_suggesting_fails_the_courses_stay_unmatched_with_a_notice() -> None:
    def fails(_courses, _school):  # type: ignore[no-untyped-def]
        raise RuntimeError("no login")

    reading = read_transcript(LINES, suggest=fails)
    assert [u.suggestion for u in reading.unmatched] == [None, None]
    assert reading.notice and "TES" in reading.notice


def test_a_cccs_course_keeps_the_free_elective_rule_when_claude_has_nothing_better() -> None:
    lines = ["Front Range Community College", "Fall 2023", "ENG 1021 English Composition I B 3.000"]
    reading = read_transcript(lines, suggest=lambda courses, _s: [None for _ in courses])
    assert [(u.suggestion, u.suggested_by) for u in reading.unmatched] == [("FREE1XX", "rule")]


def test_a_course_with_its_lab_is_offered_a_mines_lecture_and_lab_together_and_never_a_lab_alone() -> None:
    from degree_planner_backend.agent.transcript_matcher import _lab_pairs, with_lab_pairs

    full = with_lab_pairs(CATALOG)
    with_lab = [m.code for m in shortlist(OutsideCourse("CHEM 3411 + CHEM 3418", "Organic Chemistry I (with Organic Chemistry Lab I)", 5), full)]
    assert with_lab[0] == "CHGN221+CHGN223"
    alone = [m.code for m in shortlist(OutsideCourse("CHEM 3411", "Organic Chemistry I", 3), full)]
    assert "CHGN221" in alone and not any("+" in c for c in alone[:4])
    labs = set(_lab_pairs())
    assert not labs & set(with_lab) and not labs & set(alone)  # e.g. CHGN223 is never offered on its own


def test_suggest_accepts_a_lecture_and_lab_pair_from_the_shortlist() -> None:
    def runner(_c: list[str], _m: str, _w: Path) -> ClaudeRun:
        return ClaudeRun(result={"structured_output": {"suggestions": [
            {"index": 0, "mines_code": "CHGN221+CHGN223", "confidence": "high", "reason": "Both are organic chemistry with lab."}]}})

    out = suggest([OutsideCourse("CHEM 3411 + CHEM 3418", "Organic Chemistry I (with Organic Chemistry Lab I)", 5)], None, CATALOG, runner)
    assert out[0] is not None and out[0].mines_code == "CHGN221+CHGN223" and "Laboratory" in out[0].title
