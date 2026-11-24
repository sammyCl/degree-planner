"""BUG-044: a combined-program undergraduate may take 700-level credits before finishing the
bachelor's part only if the master's/PhD part is thesis-based (validator: Midhat)."""

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
            "program_id": "t-bs",
            "name": "Test Bachelor's",
            "degree_level": "bachelor",
            "catalog_year": "2026-2027",
            "total_credits_required": 3,
            "requirement_groups": [
                {"group_id": "gen-ed", "label": "General Ed", "kind": "all", "courses": ["HASS400"]}
            ],
        },
        {
            "program_id": "t-ms-non-thesis",
            "name": "Test Non-Thesis M.S.",
            "degree_level": "master",
            "catalog_year": "2026-2027",
            "total_credits_required": 6,
            "thesis_based": False,
            "requirement_groups": [
                {"group_id": "project", "label": "Project", "kind": "choose_credits",
                 "courses": ["CSCI700"], "credits_required": 6}
            ],
        },
        {
            "program_id": "t-ms-thesis-unknown",
            "name": "Test Unknown-Thesis M.S.",
            "degree_level": "master",
            "catalog_year": "2026-2027",
            "total_credits_required": 6,
            "requirement_groups": [
                {"group_id": "project", "label": "Project", "kind": "choose_credits",
                 "courses": ["CSCI700"], "credits_required": 6}
            ],
        },
        {
            "program_id": "t-combined-non-thesis",
            "name": "Test Combined (Non-Thesis)",
            "degree_level": "combined",
            "catalog_year": "2026-2027",
            "total_credits_required": 9,
            "requirement_groups": [],
            "combines": ["t-bs", "t-ms-non-thesis"],
        },
        {
            "program_id": "t-combined-unknown-thesis",
            "name": "Test Combined (Unknown Thesis)",
            "degree_level": "combined",
            "catalog_year": "2026-2027",
            "total_credits_required": 9,
            "requirement_groups": [],
            "combines": ["t-bs", "t-ms-thesis-unknown"],
        },
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(program_id: str, semesters: list[list[tuple[str, float]]]) -> Plan:
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
        student=Student(degree_level="combined", programs=[program_id], catalog_year="2026-2027"),
        semesters=plan_semesters,
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def test_700_level_before_the_bachelor_s_is_done_is_flagged_in_a_non_thesis_program(
    connection: sqlite3.Connection,
) -> None:
    plan = _plan("t-combined-non-thesis", [[("CSCI700", 6.0)], [("HASS400", 3.0)]])

    result = check_plan(connection, plan)

    ineligible = [f for f in result.flags if f.type == "ineligible_course"]
    assert len(ineligible) == 1
    assert ineligible[0].course_id == "s0-CSCI700"
    assert ineligible[0].severity == "error"


def test_700_level_after_the_bachelor_s_is_done_is_not_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-combined-non-thesis", [[("HASS400", 3.0)], [("CSCI700", 6.0)]])

    result = check_plan(connection, plan)

    assert not [f for f in result.flags if f.type == "ineligible_course"]


def test_unknown_thesis_status_is_not_flagged(connection: sqlite3.Connection) -> None:
    plan = _plan("t-combined-unknown-thesis", [[("CSCI700", 6.0)], [("HASS400", 3.0)]])

    result = check_plan(connection, plan)

    assert not [f for f in result.flags if f.type == "ineligible_course"]
