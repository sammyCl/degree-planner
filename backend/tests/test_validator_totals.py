"""The required credit total with a minor or ASI (BUG-037; validator: Midhat, fix by Samantha with Claude).
A minor or ASI adds no total of its own on top of a degree; alone, its own total counts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def program(program_id: str, level: str, total: float) -> dict:
    return {"program_id": program_id, "name": program_id, "degree_level": level, "catalog_year": "2026-2027",
            "total_credits_required": total, "requirement_groups": []}


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    programs = [program("t-bs", "bachelor", 120), program("t-bs2", "bachelor", 130), program("t-ms", "master", 30),
                program("t-minor", "minor", 18), program("t-asi", "asi", 12)]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def required(connection: sqlite3.Connection, programs: list[str], level: str = "bachelor") -> float:
    empty = Plan(student=Student(degree_level=level, programs=programs, catalog_year="2026-2027"),
                 semesters=[Semester(semester_id="s1", label="Fall 2026")],
                 summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False))
    return check_plan(connection, empty).summary.total_credits_required


@pytest.mark.parametrize("programs, total", [
    (["t-bs"], 120),
    (["t-bs", "t-minor"], 120),  # was 138
    (["t-bs", "t-minor", "t-asi"], 120),
    (["t-bs", "t-ms"], 150),  # two degrees still add up
    (["t-bs", "t-bs2", "t-minor"], 250),
    (["t-minor"], 18),  # a minor alone keeps its own total
    (["t-minor", "t-asi"], 30),
    (["t-bs", "unknown-minor"], 120),
])
def test_required_total(connection: sqlite3.Connection, programs: list[str], total: float) -> None:
    assert required(connection, programs) == total


def test_examples_4_and_5_on_the_real_data() -> None:
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    assert required(conn, ["ams-bs-cam", "computer-science-minor"]) == 120
    assert required(conn, ["cs-bs-ms-combined", "geophysics-geophysical-engineering-minor"], "combined") == 154
