"""Input-validation hardening for the data format and the loader (backend: Midhat).

BUG-007, 009, 011 (normalization only), 018, 019 (data format and data loader), BUG-013 and
BUG-020, 023(b) (lookups), BUG-029, 030, 031 (plan format), BUG-033 (transcript parser).

BUG-010, 014, 017, 022, 023(a) and BUG-028 are held back: agent/tools.py has existing adversarial
tests built against the current lenient load-then-warn-at-the-tool-layer behavior for each of
these, so rejecting the bad values at the model/loader instead needs reconciling with Samantha's
code and tests first (see bugs.txt)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.lookups import AmbiguousLookupError, catalog_years, program_ids
from degree_planner_backend.models import Course
from degree_planner_backend.plan_models import CompletedCourse, Edge, Plan, Student
from degree_planner_backend.transcript_parser import _parse_transcript_lines

GOOD_COURSE = {
    "code": "MATH112", "subject": "MATH", "number": "112", "title": "Calculus I", "credits": 4.0,
    "description": "", "catalog_year": "2026-2027",
}


def _course(**overrides: object) -> dict:
    return {**GOOD_COURSE, **overrides}


GOOD_PROGRAM = {
    "program_id": "t-bs", "name": "Test", "degree_level": "bachelor", "catalog_year": "2026-2027",
    "total_credits_required": 120, "requirement_groups": [],
}

GOOD_FORM = {"form_id": "a-form", "name": "A Form", "applies_to": ["any"]}


# --- BUG-007: NaN/infinity credits ---------------------------------------------------------------

@pytest.mark.parametrize("credits", [float("nan"), float("inf"), float("-inf")])
def test_course_rejects_non_finite_credits(credits: float) -> None:
    with pytest.raises(ValidationError):
        Course.model_validate(_course(credits=credits))


# --- BUG-009: a course round-trips through the loader's own serialization ------------------------

def _nested_exception(depth: int) -> dict:
    req: dict = {"type": "exception", "label": "base"}
    for i in range(depth):
        req = {"type": "AND" if i % 2 == 0 else "OR", "of": [req]}
    return req


def test_loader_rejects_a_course_whose_prerequisites_are_too_deep(tmp_path: Path) -> None:
    (tmp_path / "deep.json").write_text(
        json.dumps({"courses": [_course(code="MATH112", prerequisites=_nested_exception(150))]})
    )
    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)
    assert not report.ok
    assert report.courses_loaded == 0


# --- BUG-011: course codes are normalized (the shape check is held back, see module docstring) ---

def test_course_code_is_uppercased_and_despaced() -> None:
    assert Course.model_validate(_course(code="  math112  ")).code == "MATH112"
    assert Course.model_validate(_course(code="csci 200")).code == "CSCI200"


# --- BUG-018: a duplicate form_id across files is reported, not silently replaced ------------------

def test_loader_reports_a_duplicate_form_id(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(json.dumps({"forms": [{**GOOD_FORM, "notes": "first"}]}))
    (tmp_path / "b.json").write_text(json.dumps({"forms": [{**GOOD_FORM, "notes": "second"}]}))
    connection = sqlite3.connect(":memory:")

    report = refresh_database(tmp_path, connection)

    assert not report.ok
    assert any("a-form" in message for errors in report.errors.values() for message in errors)
    # last one wins, same as before the fix
    stored = json.loads(connection.execute("SELECT data FROM forms WHERE form_id = 'a-form'").fetchone()[0])
    assert stored["notes"] == "second"


# --- BUG-019: a form takes the file's catalog_year when it doesn't set its own ---------------------

def test_loader_fills_a_form_s_catalog_year_from_the_file(tmp_path: Path) -> None:
    (tmp_path / "forms.json").write_text(json.dumps({"catalog_year": "2026-2027", "forms": [GOOD_FORM]}))
    connection = sqlite3.connect(":memory:")

    report = refresh_database(tmp_path, connection)

    assert report.ok
    stored = json.loads(connection.execute("SELECT data FROM forms WHERE form_id = 'a-form'").fetchone()[0])
    assert stored["catalog_year"] == "2026-2027"


def test_a_form_s_own_catalog_year_is_not_overridden(tmp_path: Path) -> None:
    (tmp_path / "forms.json").write_text(
        json.dumps({"catalog_year": "2026-2027", "forms": [{**GOOD_FORM, "catalog_year": "2025-2026"}]})
    )
    connection = sqlite3.connect(":memory:")

    report = refresh_database(tmp_path, connection)

    assert report.ok
    stored = json.loads(connection.execute("SELECT data FROM forms WHERE form_id = 'a-form'").fetchone()[0])
    assert stored["catalog_year"] == "2025-2026"


# --- BUG-023(b): AmbiguousLookupError carries years as data, not just embedded in the message -----

def test_ambiguous_lookup_error_carries_years_as_data() -> None:
    exc = AmbiguousLookupError("'x' exists in catalog years ['2025-2026', '2026-2027']; pass", ["2025-2026", "2026-2027"])
    assert exc.years == ["2025-2026", "2026-2027"]


def test_ambiguous_lookup_error_years_defaults_to_empty() -> None:
    assert AmbiguousLookupError("message only").years == []


# --- BUG-013 / BUG-020: listing loaded catalog years and program ids --------------------------------

def test_catalog_years_and_program_ids(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text(json.dumps({
        "courses": [_course(catalog_year="2026-2027"), _course(code="MATH113", catalog_year="2025-2026")],
        "programs": [GOOD_PROGRAM, {**GOOD_PROGRAM, "program_id": "t-ms", "degree_level": "master"}],
    }))
    connection = sqlite3.connect(":memory:")
    refresh_database(tmp_path, connection)

    assert catalog_years(connection) == ["2025-2026", "2026-2027"]
    assert program_ids(connection) == ["t-bs", "t-ms"]


# --- BUG-029/030/031: plan-format models -------------------------------------------------------------

def test_completed_course_rejects_negative_credits_but_allows_zero() -> None:
    with pytest.raises(ValidationError):
        CompletedCourse.model_validate({"code": "MATH112", "credits": -4, "term": "transfer"})
    zero = CompletedCourse.model_validate({"code": "EENG500", "credits": 0, "term": "transfer"})
    assert zero.credits == 0


def test_student_rejects_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Student.model_validate(
            {"degree_level": "bachelor", "programs": ["t-bs"], "catalog_year": "2026-2027", "notes": "no Fridays"}
        )


def test_edge_dumps_as_from_by_default() -> None:
    edge = Edge(**{"from": "a", "to": "b"})
    assert json.loads(edge.model_dump_json()) == {"from": "a", "to": "b"}


def test_plan_round_trips_through_the_plan_store_s_by_alias_dump(tmp_path: Path) -> None:
    from degree_planner_backend.plan_models import PlannedCourse, Semester, Summary

    plan = Plan(
        student=Student(degree_level="bachelor", programs=["t-bs"], catalog_year="2026-2027"),
        semesters=[Semester(semester_id="s1", label="Fall 2026", courses=[
            PlannedCourse(course_id="c1", code="MATH112", title="Calculus I", credits=4.0, status="planned")
        ])],
        prerequisite_edges=[Edge(**{"from": "a", "to": "b"})],
        summary=Summary(total_credits=4, total_credits_required=120, requirements_met=False),
    )
    restored = Plan.model_validate_json(plan.model_dump_json())
    assert restored == plan


# --- BUG-033: transcript term headings need ASCII digits and a sensible year -------------------------

def test_transcript_ignores_a_term_heading_with_a_year_too_old() -> None:
    lines = ["SUMMER 0001", "MATH112 Calculus I 4.00"]
    assert _parse_transcript_lines(lines) == []


def test_transcript_ignores_full_width_digits_in_a_term_heading() -> None:
    lines = ["Fall ２０２６", "MATH112 Calculus I 4.00"]
    assert _parse_transcript_lines(lines) == []


def test_transcript_accepts_a_normal_term_heading() -> None:
    lines = ["Fall 2026", "MATH112 Calculus I 4.00"]
    courses = _parse_transcript_lines(lines)
    assert len(courses) == 1
    assert courses[0].term == "Fall 2026"
