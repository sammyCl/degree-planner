"""MATH225's corequisite on the real data: CSCI128 (or CSCI102) satisfies it (data/CONFLICT-LOG.md, 2026-11-26).
The catalog CSV said "CSC128", which is not a course, so a plan with CSCI128 and no CSCI102 always failed."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def math225_flags(semesters: list[tuple[str, list[str]]]) -> list[str]:
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    plan = Plan(
        student=Student(degree_level="bachelor", programs=["cs-bs-general-track"], catalog_year="2026-2027"),
        semesters=[
            Semester(
                semester_id=f"s{i}",
                label=label,
                courses=[PlannedCourse(course_id=f"{i}-{c}", code=c, title=c, credits=3, status="planned") for c in codes],
                total_credits=3 * len(codes),
            )
            for i, (label, codes) in enumerate(semesters)
        ],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    return [f.message for f in check_plan(conn, plan).flags if f.course_id and f.course_id.endswith("MATH225")]


def test_csci128_in_an_earlier_semester_satisfies_math225() -> None:
    assert math225_flags([("Fall 2026", ["MATH111", "CSCI128"]), ("Spring 2027", ["MATH112"]), ("Fall 2027", ["MATH225"])]) == []


def test_math225_still_needs_one_of_them() -> None:
    flags = math225_flags([("Fall 2026", ["MATH111"]), ("Spring 2027", ["MATH112"]), ("Fall 2027", ["MATH225"])])
    assert len(flags) == 1 and "CSCI128 or CSCI102" in flags[0]
