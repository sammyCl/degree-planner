"""The minor and ASI overlap rule in the validator (BUG-036; validator: Midhat, fix by Samantha with
Claude): at least 9 of an add-on's credits must not also be used for the degree, except free electives."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
CODES = ["A100", "B100", "C100", "D100", "E100", "F100", "G100", "H100"]


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    courses = [{"code": c, "subject": "AAAA", "number": c[1:], "title": c, "credits": 3.0, "description": "",
                "catalog_year": "2026-2027"} for c in CODES]
    major = {"program_id": "t-bs", "name": "Major", "degree_level": "bachelor", "catalog_year": "2026-2027",
             "total_credits_required": 15, "requirement_groups": [
                 {"group_id": "req", "label": "req", "kind": "all", "courses": ["A100", "B100"]},
                 {"group_id": "pick", "label": "pick", "kind": "choose_credits", "courses": ["C100", "D100"],
                  "credits_required": 3},
                 {"group_id": "free", "label": "free", "kind": "choose_credits", "credits_required": 6}]}

    def add_on(program_id: str, level: str) -> dict:
        return {"program_id": program_id, "name": program_id, "degree_level": level, "catalog_year": "2026-2027",
                "total_credits_required": 12, "requirement_groups": [
                    {"group_id": "core", "label": "core", "kind": "all", "courses": ["A100", "E100"]},
                    {"group_id": "pick", "label": "pick", "kind": "choose_credits",
                     "courses": ["C100", "F100", "G100"], "credits_required": 6}]}

    (tmp_path / "courses.json").write_text(json.dumps({"courses": courses}))
    (tmp_path / "programs.json").write_text(json.dumps({"programs": [major, add_on("t-minor", "minor"),
                                                                     add_on("t-asi", "asi")]}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def plan(programs: list[str], *semesters: list[str], level: str = "bachelor") -> Plan:
    return Plan(
        student=Student(degree_level=level, programs=programs, catalog_year="2026-2027"),
        semesters=[Semester(semester_id=f"s{i}", label=f"S{i}", courses=[
            PlannedCourse(course_id=f"s{i}-{c}", code=c, title=c, credits=3.0, status="planned") for c in codes])
            for i, codes in enumerate(semesters)],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def overlap_errors(checked: Plan) -> list[str]:
    return [f.message for f in checked.flags if f.severity == "error" and "not also used for the degree" in f.message]


def test_a_minor_mostly_made_of_major_courses_is_flagged(connection) -> None:
    # A100 (major "all") and C100 (the major's only pick) are shared; only E100 is not: 3 < 9.
    checked = check_plan(connection, plan(["t-bs", "t-minor"], ["A100", "B100", "C100"], ["E100", "H100"]))
    (message,) = overlap_errors(checked)
    assert message.startswith("t-minor: only 3 of its credits")
    assert "shared: A100, C100" in message
    assert not checked.summary.requirements_met


def test_free_electives_and_spare_courses_are_not_shared(connection) -> None:
    # D100 fills the major's pick, so C100 is spare; with E100 and F100: 9 unshared (A100 shared).
    checked = check_plan(connection, plan(["t-bs", "t-minor"], ["A100", "B100", "C100", "D100"], ["E100", "F100"]))
    assert overlap_errors(checked) == []


def test_an_asi_follows_the_same_rule(connection) -> None:
    checked = check_plan(connection, plan(["t-bs", "t-asi"], ["A100", "B100", "C100"], ["E100", "H100"]))
    assert overlap_errors(checked) == [overlap_errors(checked)[0]]
    assert overlap_errors(checked)[0].startswith("t-asi:")


def test_a_minor_alone_has_nothing_to_overlap(connection) -> None:
    checked = check_plan(connection, plan(["t-minor"], ["A100", "B100", "C100"], ["E100"], level="minor"))
    assert overlap_errors(checked) == []


def test_example_4_overlap_on_the_real_data_is_flagged() -> None:
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    checked = check_plan(conn, plan(["ams-bs-cam", "computer-science-minor"],
                                    ["CSCI200", "MATH334"], ["MATH307", "CSCI220"], ["CSCI210", "CSCI403"]))
    (message,) = overlap_errors(checked)
    assert "Minor in Computer Science" in message
    for code in ("CSCI200", "MATH334", "MATH307"):
        assert code in message
