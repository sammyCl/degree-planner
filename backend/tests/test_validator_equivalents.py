"""Equivalent courses in the validator (BUG-041; validator: Midhat, fix by Samantha with Claude).
An equivalent course satisfies a prerequisite, and of a set of equivalent courses only one counts
toward requirements and credits."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.models import Course
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def course(code: str, credits: float = 3.0, equivalent: list[str] | None = None, prereq: str | None = None) -> dict:
    data = {"code": code, "subject": code[:4], "number": code[4:], "title": code, "credits": credits,
            "description": "", "catalog_year": "2026-2027",
            "prerequisites": {"type": "course", "code": prereq} if prereq else None}
    if equivalent:
        data["equivalent_with"] = equivalent
    return data


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    courses = [
        course("MATH213", 4, ["MATH223"]), course("MATH223", 4, ["MATH213"]),
        course("HASS100", 3, ["HNRS105", "HNRS115"]), course("HNRS105", 3, ["HASS100"]),
        course("HNRS115", 4, ["HASS100"]), course("HASS200", prereq="HASS100"),
        course("MATH225", prereq="MATH213"), course("FREE101"), course("FREE102"),
    ]
    program = {"program_id": "t-bs", "name": "Test BS", "degree_level": "bachelor", "catalog_year": "2026-2027",
               "total_credits_required": 14, "requirement_groups": [
                   {"group_id": "req", "label": "Required", "kind": "all", "courses": ["MATH213"]},
                   {"group_id": "pick", "label": "One of", "kind": "choose_credits",
                    "courses": ["HASS100", "FREE101"], "credits_required": 3},
                   {"group_id": "free", "label": "Free", "kind": "choose_credits", "credits_required": 7}]}
    (tmp_path / "courses.json").write_text(json.dumps({"courses": courses}))
    (tmp_path / "programs.json").write_text(json.dumps({"programs": [program]}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def plan(semesters: list[list[str]], completed: list[tuple[str, float]] = (), credits: dict[str, float] | None = None) -> Plan:
    credits = {"MATH213": 4, "MATH223": 4, "HNRS115": 4} | (credits or {})
    return Plan(
        student=Student(degree_level="bachelor", programs=["t-bs"], catalog_year="2026-2027",
                        completed_courses=[{"code": c, "credits": cr, "term": "Fall 2025"} for c, cr in completed]),
        semesters=[Semester(semester_id=f"s{i}", label=f"S{i}", courses=[
            PlannedCourse(course_id=f"s{i}-{c}", code=c, title=c, credits=credits.get(c, 3.0), status="planned")
            for c in codes]) for i, codes in enumerate(semesters)],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def errors(checked: Plan) -> list[str]:
    return [f.message for f in checked.flags if f.severity == "error"]


def test_an_equivalent_course_satisfies_a_prerequisite(connection) -> None:
    # A Thorson student: HNRS105 completed, so HASS200 (prerequisite HASS100) is fine.
    checked = check_plan(connection, plan([["HASS200", "MATH213"], ["MATH225", "FREE101"]], completed=[("HNRS105", 3)]))
    assert not any("HASS200 requires" in m for m in errors(checked))


def test_without_the_equivalent_the_prerequisite_is_still_broken(connection) -> None:
    checked = check_plan(connection, plan([["HASS200", "MATH213"], ["MATH225", "FREE101"]]))
    assert any("HASS200 requires HASS100" in m for m in errors(checked))


def test_the_honors_version_fills_the_required_course_and_its_prerequisites(connection) -> None:
    checked = check_plan(connection, plan([["MATH223", "FREE101"], ["MATH225", "FREE102", "HASS100"]]))
    assert errors(checked) == []
    assert checked.summary.requirements_met


def test_two_equivalent_courses_count_once(connection) -> None:
    # MATH213 + MATH223: the second adds no credits, so 4 + 3 + 3 + 3 = 13 of 14 counts.
    checked = check_plan(connection, plan([["MATH213", "FREE101"], ["MATH223", "FREE102", "MATH225"]]))
    warning = next(f for f in checked.flags if f.severity == "warning" and "equivalent" in f.message)
    assert warning.message.startswith("MATH223 is equivalent to MATH213")
    assert warning.course_id == "s1-MATH223"
    assert checked.summary.total_credits == 13
    assert any("Plan has 13.0 credits; needs 14" in m for m in errors(checked))


def test_a_completed_course_counts_before_a_planned_equivalent(connection) -> None:
    checked = check_plan(connection, plan([["MATH213", "FREE101", "FREE102"]], completed=[("MATH223", 4)]))
    warning = next(f for f in checked.flags if "equivalent" in f.message)
    assert warning.message.startswith("MATH213 is equivalent to MATH223")


def test_the_real_data_links_the_examples_equivalents() -> None:
    courses = {c["code"]: Course.model_validate(c)
               for c in json.loads((REPO_ROOT / "data" / "json" / "courses.json").read_text())["courses"]}
    assert courses["MATH213"].equivalent_with == ["MATH223"]
    assert "MATH213" in courses["MATH223"].equivalent_with
    assert {"HNRS105", "HNRS115"} <= set(courses["HASS100"].equivalent_with)
    for code, c in courses.items():  # always both ways, and only real catalog codes
        for other in c.equivalent_with:
            assert code in courses[other].equivalent_with, (code, other)
