"""BUG-042: an "all" group's course required every fall/spring semester (e.g. EENG500 Graduate
Seminar) isn't met by appearing once anywhere in the plan (validator: Midhat)."""

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
    programs = [
        {
            "program_id": "t-ms",
            "name": "Test M.S.",
            "degree_level": "master",
            "catalog_year": "2026-2027",
            "total_credits_required": 30,
            "requirement_groups": [
                {"group_id": "seminar", "label": "Graduate Seminar", "kind": "all",
                 "courses": ["EENG500"], "every_semester": True},
            ],
        },
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(semesters: list[tuple[str, list[str]]]) -> Plan:
    plan_semesters = [
        Semester(
            semester_id=f"s{i}",
            label=label,
            courses=[
                PlannedCourse(course_id=f"s{i}-{code}", code=code, title=code, credits=0.0, status="planned")
                for code in codes
            ],
        )
        for i, (label, codes) in enumerate(semesters)
    ]
    return Plan(
        student=Student(degree_level="master", programs=["t-ms"], catalog_year="2026-2027"),
        semesters=plan_semesters,
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def _seminar_flags(plan: Plan, connection: sqlite3.Connection) -> list[str]:
    result = check_plan(connection, plan)
    return [f.message for f in result.flags if f.type == "requirement_unmet" and "Seminar" in f.message]


def test_a_missed_fall_or_spring_semester_is_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan([("Fall 2026", ["EENG500"]), ("Spring 2027", [])])

    flags = _seminar_flags(plan, connection)

    assert len(flags) == 1
    assert "Spring 2027" in flags[0]


def test_every_fall_and_spring_semester_covered_is_not_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan([("Fall 2026", ["EENG500"]), ("Spring 2027", ["EENG500"])])

    assert not _seminar_flags(plan, connection)


def test_a_summer_semester_does_not_need_it(connection: sqlite3.Connection) -> None:
    plan = _plan([("Fall 2026", ["EENG500"]), ("Summer 2027", []), ("Spring 2027", ["EENG500"])])

    assert not _seminar_flags(plan, connection)
