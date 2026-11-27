"""A master's or PhD course's undergraduate prerequisite is assumed from the bachelor's degree (a warning to confirm),
and the honors-twin prerequisite typos found in the all-programs sweep (2026-11-26). Real catalog data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    return conn


def flags(connection: sqlite3.Connection, level: str, program: str, semesters: list[list[str]], code: str) -> list[tuple[str, str]]:
    labels = ["Fall 2027", "Spring 2028", "Fall 2028"]
    plan = Plan(
        student=Student(degree_level=level, programs=[program], catalog_year="2026-2027"),
        semesters=[
            Semester(semester_id=f"s{i}", label=labels[i], courses=[
                PlannedCourse(course_id=f"{i}-{c}", code=c, title=c, credits=3, status="planned") for c in codes])
            for i, codes in enumerate(semesters)
        ],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    return [(f.type, f.severity) for f in check_plan(connection, plan).flags
            if f.course_id and f.course_id.endswith(code) and f.type != "exception_claimed"]


def test_a_masters_course_with_an_undergraduate_prerequisite_is_to_confirm(connection: sqlite3.Connection) -> None:
    assert flags(connection, "master", "data-science-ms", [["MATH530"]], "MATH530") == [("undergraduate_prerequisite", "warning")]


def test_a_bachelors_student_still_gets_the_error(connection: sqlite3.Connection) -> None:
    assert flags(connection, "bachelor", "cs-bs-general-track", [["MATH530"]], "MATH530") == [("broken_prerequisite", "error")]


def test_a_prerequisite_the_plan_holds_too_late_is_still_out_of_order(connection: sqlite3.Connection) -> None:
    assert flags(connection, "master", "data-science-ms", [["MATH530"], ["MATH334"]], "MATH530") == [("broken_prerequisite", "error")]


def test_a_graduate_prerequisite_is_never_assumed(connection: sqlite3.Connection) -> None:
    # CSCI581 needs PHGN519, a graduate course
    assert flags(connection, "master", "quantum-engineering-ms", [["CSCI581"]], "CSCI581") == [("broken_prerequisite", "error")]


@pytest.mark.parametrize("code, earlier", [
    ("MATH342", ["MATH213"]),
    ("PHGN320", ["PHGN300", "PHGN310", "MATH332"]),
])
def test_either_version_of_a_course_is_enough(connection: sqlite3.Connection, code: str, earlier: list[str]) -> None:
    result = flags(connection, "bachelor", "engineering-physics-bs", [earlier, [code]], code)
    assert result == []


# ---------- summer courses ----------

def _summer_flags(connection: sqlite3.Connection, terms: list[tuple[str, list[str]]]) -> list[str]:
    plan = Plan(
        student=Student(degree_level="bachelor", programs=["cs-bs-general-track"], catalog_year="2026-2027"),
        semesters=[
            Semester(semester_id=f"s{i}", label=label, courses=[
                PlannedCourse(course_id=f"{i}-{c}", code=c, title=c, credits=3, status="planned") for c in codes])
            for i, (label, codes) in enumerate(terms)
        ],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    return [f.message for f in check_plan(connection, plan).flags if f.type == "summer_course"]


def test_a_field_session_in_fall_is_flagged_and_in_summer_is_not(connection: sqlite3.Connection) -> None:
    assert _summer_flags(connection, [("Summer 2029", ["CSCI370"])]) == []
    [moved] = _summer_flags(connection, [("Summer 2029", []), ("Fall 2029", ["CSCI370"])])
    assert "CSCI370 is taken in summer" in moved and "Move it to a summer semester" in moved
    [none] = _summer_flags(connection, [("Fall 2029", ["CSCI370"])])
    assert "confirm with your advisor" in none
