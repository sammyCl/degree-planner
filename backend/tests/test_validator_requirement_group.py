"""BUG-038: a "requirement" group is met only by one of the combinations its expression names,
never a mix (e.g. the Thorson first-year-core swap: HASS100+EDNS151, or HNRS105+HNRS115, never
HASS100+HNRS105) (validator: Midhat)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

SWAP = {
    "type": "OR",
    "of": [
        {"type": "AND", "of": [{"type": "course", "code": "HASS100"}, {"type": "course", "code": "EDNS151"}]},
        {"type": "AND", "of": [{"type": "course", "code": "HNRS105"}, {"type": "course", "code": "HNRS115"}]},
    ],
}


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    programs = [
        {
            "program_id": "t-bs",
            "name": "Test Bachelor's",
            "degree_level": "bachelor",
            "catalog_year": "2026-2027",
            "total_credits_required": 6,
            "requirement_groups": [
                {
                    "group_id": "first-year-core",
                    "label": "HASS100 and EDNS151, or HNRS105 and HNRS115",
                    "kind": "requirement",
                    "credits_required": 6,
                    "requirement": SWAP,
                },
            ],
        },
    ]
    # the courses must be in the catalog: a code the data does not have is "confirm with your advisor" instead
    courses = [
        {"code": code, "subject": code[:4], "number": code[4:], "title": code, "description": "", "credits": 3, "catalog_year": "2026-2027"}
        for code in ("HASS100", "EDNS151", "HNRS105", "HNRS115")
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"courses": courses, "programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def _plan(codes_and_credits: list[tuple[str, float]]) -> Plan:
    courses = [
        PlannedCourse(course_id=f"c{i}", code=code, title=code, credits=credits, status="planned")
        for i, (code, credits) in enumerate(codes_and_credits)
    ]
    return Plan(
        student=Student(degree_level="bachelor", programs=["t-bs"], catalog_year="2026-2027"),
        semesters=[Semester(semester_id="s1", label="Fall 2026", courses=courses)],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def _unmet(plan: Plan, connection: sqlite3.Connection) -> list[str]:
    result = check_plan(connection, plan)
    return [f.message for f in result.flags if f.type == "requirement_unmet"]


def test_the_core_pair_satisfies_the_group(connection: sqlite3.Connection) -> None:
    plan = _plan([("HASS100", 3.0), ("EDNS151", 3.0)])
    assert not _unmet(plan, connection)


def test_the_honors_pair_satisfies_the_group(connection: sqlite3.Connection) -> None:
    plan = _plan([("HNRS105", 3.0), ("HNRS115", 4.0)])
    assert not _unmet(plan, connection)


def test_a_mix_of_the_two_pairs_does_not_satisfy_the_group(connection: sqlite3.Connection) -> None:
    plan = _plan([("HASS100", 3.0), ("HNRS105", 3.0)])
    unmet = _unmet(plan, connection)
    assert len(unmet) == 1
    assert "needs" in unmet[0]


def test_neither_pair_does_not_satisfy_the_group(connection: sqlite3.Connection) -> None:
    plan = _plan([])
    assert len(_unmet(plan, connection)) == 1
