"""A requirement the course data cannot fill is "confirm with your advisor", not a failed plan
(team member's call, 2026-11-26: Additive Manufacturing ASI requires AMFG401, which the catalog data lacks)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

YEAR = "2026-2027"


def course(code: str, credits: float = 3) -> dict:
    return {"code": code, "subject": code[:4], "number": code[4:], "title": code, "description": "", "credits": credits, "catalog_year": YEAR}


def program(groups: list[dict]) -> dict:
    return {"program_id": "t-bs", "name": "Test", "degree_level": "bachelor", "catalog_year": YEAR,
            "total_credits_required": 3, "requirement_groups": groups}


def check(tmp_path: Path, groups: list[dict], codes: list[str]) -> Plan:
    data = {"courses": [course("MATH111"), course("MATH112"), course("SEMN500", 1)], "programs": [program(groups)]}
    (tmp_path / "data.json").write_text(json.dumps(data))
    connection = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, connection).ok
    courses = [PlannedCourse(course_id=f"c{i}", code=c, title=c, credits=1 if c == "SEMN500" else 3, status="planned") for i, c in enumerate(codes)]
    return check_plan(connection, Plan(
        student=Student(degree_level="bachelor", programs=["t-bs"], catalog_year=YEAR),
        semesters=[Semester(semester_id="s1", label="Fall 2026", courses=courses)],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    ))


def kinds(plan: Plan) -> list[tuple[str, str]]:
    return [(f.type, f.severity) for f in plan.flags]


def test_a_required_course_missing_from_the_catalog_is_a_confirm_warning(tmp_path: Path) -> None:
    plan = check(tmp_path, [{"group_id": "required", "label": "Required", "kind": "all", "courses": ["MATH111", "GONE401"]}], ["MATH111"])
    assert kinds(plan) == [("unlisted_course", "warning")]
    assert "GONE401" in plan.flags[0].message and "Confirm with your advisor" in plan.flags[0].message
    assert plan.summary.requirements_met
    assert [(s.met, s.confirm) for s in plan.requirement_status or []] == [(False, True)]


def test_a_missing_course_the_catalog_has_is_still_an_error(tmp_path: Path) -> None:
    plan = check(tmp_path, [{"group_id": "required", "label": "Required", "kind": "all", "courses": ["MATH112", "GONE401"]}], ["MATH111"])
    assert sorted(kinds(plan)) == [("requirement_unmet", "error"), ("unlisted_course", "warning")]
    assert not plan.summary.requirements_met
    assert [s.confirm for s in plan.requirement_status or []] == [False]


@pytest.mark.parametrize("planned, expected", [
    (["SEMN500", "MATH111"], [("unlisted_course", "warning")]),  # every listed course is in: the rest is the data's gap
    (["MATH111"], [("credit_shortfall", "error")]),  # the student can still plan the listed course
])
def test_a_group_whose_listed_courses_cannot_add_up(tmp_path: Path, planned: list[str], expected: list) -> None:
    group = {"group_id": "seminar", "label": "Seminar", "kind": "choose_credits", "courses": ["SEMN500"], "credits_required": 2}
    assert kinds(check(tmp_path, [group], planned)) == expected


def test_a_short_group_the_catalog_could_fill_is_still_an_error(tmp_path: Path) -> None:
    group = {"group_id": "pick", "label": "Pick", "kind": "choose_credits", "courses": ["MATH111", "MATH112"], "credits_required": 6}
    assert kinds(check(tmp_path, [group], ["MATH111"])) == [("credit_shortfall", "error")]


def test_a_required_choice_that_only_a_missing_course_could_meet(tmp_path: Path) -> None:
    rule = {"type": "AND", "of": [{"type": "course", "code": "MATH111"}, {"type": "course", "code": "GONE401"}]}
    group = {"group_id": "core", "label": "Core", "kind": "requirement", "credits_required": 6, "requirement": rule}
    assert kinds(check(tmp_path, [group], ["MATH111"])) == [("unlisted_course", "warning")]
    assert ("requirement_unmet", "error") in kinds(check(tmp_path, [group], []))
