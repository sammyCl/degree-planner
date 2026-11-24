"""BUG-043: a graduate elective group with no fixed course list must not be filled by an
undergraduate-level course (validator: Midhat)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan


def _program(program_id: str, level: str, groups: list[dict]) -> dict:
    return {
        "program_id": program_id,
        "name": program_id,
        "degree_level": level,
        "catalog_year": "2026-2027",
        "total_credits_required": 9,
        "requirement_groups": groups,
    }


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    programs = [
        _program(
            "t-ms",
            "master",
            [{"group_id": "electives", "label": "Electives", "kind": "choose_credits", "credits_required": 6}],
        ),
        _program(
            "t-bs",
            "bachelor",
            [{"group_id": "electives", "label": "Electives", "kind": "choose_credits", "credits_required": 6}],
        ),
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(program_id: str, level: str, codes_and_credits: list[tuple[str, float]]) -> Plan:
    courses = [
        PlannedCourse(course_id=f"c{i}", code=code, title=code, credits=credits, status="planned")
        for i, (code, credits) in enumerate(codes_and_credits)
    ]
    return Plan(
        student=Student(degree_level=level, programs=[program_id], catalog_year="2026-2027"),
        semesters=[Semester(semester_id="s1", label="Fall 2026", courses=courses)],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def test_undergraduate_courses_dont_fill_a_graduate_electives_group(connection: sqlite3.Connection) -> None:
    plan = _plan("t-ms", "master", [("CSCI403", 3.0), ("CSCI562", 3.0)])

    result = check_plan(connection, plan)

    shortfalls = [f for f in result.flags if f.type == "credit_shortfall" and "Electives" in f.message]
    assert len(shortfalls) == 1
    assert "3.0" in shortfalls[0].message  # only CSCI562 (500-level) counts, not CSCI403


def test_graduate_level_courses_fill_the_group(connection: sqlite3.Connection) -> None:
    plan = _plan("t-ms", "master", [("CSCI562", 3.0), ("CSCI564", 3.0)])

    result = check_plan(connection, plan)

    assert not [f for f in result.flags if f.type == "credit_shortfall" and "Electives" in f.message]


def test_bachelor_s_electives_are_unaffected(connection: sqlite3.Connection) -> None:
    plan = _plan("t-bs", "bachelor", [("CSCI403", 3.0), ("CSCI100", 3.0)])

    result = check_plan(connection, plan)

    assert not [f for f in result.flags if f.type == "credit_shortfall" and "Electives" in f.message]
