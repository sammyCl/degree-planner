"""BUG-026(d): an OR branch that needs an exception isn't flagged once a sibling branch is already
satisfied by a plain course (validator: Midhat)."""

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
            "code": "MNGN501", "subject": "MNGN", "number": "501", "title": "Mine Design", "credits": 3.0,
            "description": "", "catalog_year": "2026-2027",
            "prerequisites": {
                "type": "OR",
                "of": [
                    {"type": "course", "code": "CSCI100"},
                    {"type": "exception", "label": "instructor approval"},
                ],
            },
        },
        {
            "code": "CSCI100", "subject": "CSCI", "number": "100", "title": "Intro", "credits": 3.0,
            "description": "", "catalog_year": "2026-2027",
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


def _exception_flags(plan: Plan, connection: sqlite3.Connection) -> list:
    result = check_plan(connection, plan)
    return [f for f in result.flags if f.type == "exception_claimed"]


def test_a_satisfied_course_branch_does_not_raise_the_sibling_exception(connection: sqlite3.Connection) -> None:
    plan = _plan([["CSCI100"], ["MNGN501"]])
    assert not _exception_flags(plan, connection)


def test_the_exception_branch_still_raises_when_the_course_branch_is_not_satisfied(
    connection: sqlite3.Connection,
) -> None:
    plan = _plan([["MNGN501"]])
    flags = _exception_flags(plan, connection)
    assert len(flags) == 1
    assert flags[0].course_id == "s0-MNGN501"
