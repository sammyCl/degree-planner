"""BUG-026(a): no semester over the Mines per-term credit limit (18 undergraduate, 15 graduate;
graduate once a combined program's bachelor's part is done) (validator: Midhat)."""

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
            "program_id": "t-bs", "name": "Test Bachelor's", "degree_level": "bachelor",
            "catalog_year": "2026-2027", "total_credits_required": 3,
            "requirement_groups": [{"group_id": "req", "label": "Req", "kind": "all", "courses": ["HASS100"]}],
        },
        {
            "program_id": "t-ms", "name": "Test M.S.", "degree_level": "master",
            "catalog_year": "2026-2027", "total_credits_required": 3,
            "requirement_groups": [{"group_id": "req", "label": "Req", "kind": "all", "courses": ["CSCI700"]}],
        },
        {
            "program_id": "t-combined", "name": "Test Combined", "degree_level": "combined",
            "catalog_year": "2026-2027", "total_credits_required": 6, "requirement_groups": [],
            "combines": ["t-bs", "t-ms"],
        },
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(program_id: str, level: str, semesters: list[list[tuple[str, float]]]) -> Plan:
    plan_semesters = [
        Semester(
            semester_id=f"s{i}",
            label=f"Semester {i}",
            courses=[
                PlannedCourse(course_id=f"s{i}-{code}", code=code, title=code, credits=credits, status="planned")
                for code, credits in courses
            ],
        )
        for i, courses in enumerate(semesters)
    ]
    return Plan(
        student=Student(degree_level=level, programs=[program_id], catalog_year="2026-2027"),
        semesters=plan_semesters,
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def _overload_flags(plan: Plan, connection: sqlite3.Connection) -> list[str]:
    result = check_plan(connection, plan)
    return [f.message for f in result.flags if f.type == "semester_overload"]


def test_19_undergraduate_credits_is_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-bs", "bachelor", [[("A", 9.0), ("B", 10.0)]])
    flags = _overload_flags(plan, connection)
    assert len(flags) == 1
    assert "18-credit" in flags[0]


def test_18_undergraduate_credits_is_not_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-bs", "bachelor", [[("A", 9.0), ("B", 9.0)]])
    assert not _overload_flags(plan, connection)


def test_16_graduate_credits_is_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-ms", "master", [[("A", 8.0), ("B", 8.0)]])
    flags = _overload_flags(plan, connection)
    assert len(flags) == 1
    assert "15-credit" in flags[0]


def test_15_graduate_credits_is_not_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-ms", "master", [[("A", 8.0), ("B", 7.0)]])
    assert not _overload_flags(plan, connection)


def test_combined_program_uses_the_undergraduate_limit_before_the_bachelor_s_is_done(
    connection: sqlite3.Connection,
) -> None:
    # 19 credits while the bachelor's requirement (HASS100) is still outstanding: undergraduate limit.
    plan = _plan("t-combined", "combined", [[("A", 10.0), ("B", 9.0)], [("HASS100", 3.0)]])
    flags = _overload_flags(plan, connection)
    assert len(flags) == 1
    assert "Semester 0" in flags[0]
    assert "18-credit" in flags[0]


def test_combined_program_uses_the_graduate_limit_after_the_bachelor_s_is_done(
    connection: sqlite3.Connection,
) -> None:
    # 16 credits in the semester after HASS100 is done: graduate limit applies.
    plan = _plan("t-combined", "combined", [[("HASS100", 3.0)], [("A", 8.0), ("B", 8.0)]])
    flags = _overload_flags(plan, connection)
    assert len(flags) == 1
    assert "Semester 1" in flags[0]
    assert "15-credit" in flags[0]
