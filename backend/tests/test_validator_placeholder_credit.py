"""Placeholder credit from a transcript (FREE1XX-1, HASS2XX-1, CSM2XX-1) fills the right requirement group.
Validator rule added for the transcript reader (validator: Midhat; added by Abdallah with Claude, 2026-11-26)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import CompletedCourse, Plan, PlannedCourse, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    return conn


def status(connection: sqlite3.Connection, completed: list[tuple[str, float]]) -> dict[str, float | None]:
    plan = Plan(
        student=Student(
            degree_level="bachelor",
            programs=["cs-bs-general-track"],
            catalog_year="2026-2027",
            completed_courses=[CompletedCourse(code=code, credits=credits, term="transfer") for code, credits in completed],
        ),
        semesters=[Semester(semester_id="s1", label="Fall 2026")],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    return {s.group_id: s.credits_earned for s in check_plan(connection, plan).requirement_status or []}


def test_hass_and_success_wellness_placeholders_fill_their_groups(connection: sqlite3.Connection) -> None:
    earned = status(connection, [("HASS2XX-1", 3), ("HASS2XX-2", 3), ("CSM2XX-1", 1), ("FREE1XX-1", 3), ("FREE1XX-2", 3)])
    assert earned["cas-mid"] == 6
    assert earned["success-wellness"] == 1
    assert earned["free-electives"] == 6  # each numbered FREE1XX row counts, not just one


def test_a_placeholder_fills_no_more_than_its_group_needs(connection: sqlite3.Connection) -> None:
    earned = status(connection, [("HASS2XX-1", 3), ("HASS2XX-2", 3), ("HASS2XX-3", 3)])
    assert earned["cas-mid"] == 6
    assert earned["free-electives"] == 3  # the extra one is a free elective


def test_a_placeholder_of_another_level_does_not_fill_the_group(connection: sqlite3.Connection) -> None:
    earned = status(connection, [("HASS1XX-1", 3)])
    assert earned["cas-mid"] == 0


def test_a_placeholder_without_its_hyphen_still_counts(connection: sqlite3.Connection) -> None:
    # the agent cleans completed codes the way it cleans model input ("HASS2XX-1" -> "HASS2XX1")
    assert status(connection, [("HASS2XX1", 3), ("HASS2XX2", 3)])["cas-mid"] == 6


def test_earned_placeholder_credit_fills_the_group_before_a_planned_course(connection: sqlite3.Connection) -> None:
    plan = Plan(
        student=Student(
            degree_level="bachelor",
            programs=["cs-bs-general-track"],
            catalog_year="2026-2027",
            completed_courses=[CompletedCourse(code=f"HASS2XX-{n}", credits=3, term="transfer") for n in (1, 2)],
        ),
        semesters=[
            Semester(
                semester_id="s1",
                label="Fall 2026",
                courses=[PlannedCourse(course_id="p1", code="HASS320", title="Ethics", credits=3, status="planned")],
                total_credits=3,
            )
        ],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )
    checked = check_plan(connection, plan)
    groups = [g.group_id for g in (checked.counts_toward or {}).get("p1", [])]
    assert "cas-mid" not in groups  # the two earned HASS 2XX credits already fill CAS mid-level
