"""BUG-049: the validator checks corequisites, met by the same semester or an earlier one, unlike
a prerequisite which must be strictly earlier (validator: Midhat)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    courses = [
        {
            "code": "HASS202", "subject": "HASS", "number": "202", "title": "Nature and Human Values II",
            "credits": 3.0, "description": "", "catalog_year": "2026-2027",
            "corequisites": {"type": "course", "code": "HASS215"},
        },
        {
            "code": "HASS215", "subject": "HASS", "number": "215", "title": "Global Studies",
            "credits": 3.0, "description": "", "catalog_year": "2026-2027",
        },
    ]
    (tmp_path / "courses.json").write_text(json.dumps({"courses": courses}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(semesters: list[list[str]]) -> Plan:
    plan_semesters = [
        Semester(
            semester_id=f"s{i}",
            label=f"Semester {i}",
            courses=[
                PlannedCourse(course_id=f"s{i}-{code}", code=code, title=code, credits=3.0, status="planned")
                for code in codes
            ],
        )
        for i, codes in enumerate(semesters)
    ]
    return Plan(
        student=Student(degree_level="bachelor", programs=["t-bs"], catalog_year="2026-2027"),
        semesters=plan_semesters,
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def _coreq_flags(plan: Plan, connection: sqlite3.Connection) -> list:
    result = check_plan(connection, plan)
    return [f for f in result.flags if f.type == "broken_prerequisite" and "corequisite" in f.message]


def test_a_later_corequisite_is_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan([["HASS202"], ["HASS215"]])
    flags = _coreq_flags(plan, connection)
    assert len(flags) == 1
    assert flags[0].course_id == "s0-HASS202"


def test_the_same_semester_satisfies_the_corequisite(connection: sqlite3.Connection) -> None:
    plan = _plan([["HASS202", "HASS215"]])
    assert not _coreq_flags(plan, connection)


def test_an_earlier_semester_satisfies_the_corequisite(connection: sqlite3.Connection) -> None:
    plan = _plan([["HASS215"], ["HASS202"]])
    assert not _coreq_flags(plan, connection)
