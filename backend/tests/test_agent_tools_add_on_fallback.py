"""BUG-053 on the agent side: a minor, ASI or certificate stored only for an older catalog year is
planned and checked against that year, as the validator already does, instead of "do not plan
against it". The agent tools call validator._add_on_with_fallback, so both use one rule.

Catalog: t-bs (bachelor's, 2026-2027, core TEST101), t-asi (ASI, only 2025-2026, core TEST201),
old-bs (bachelor's, only 2025-2026), new-minor (minor, only 2027-2028). The student is 2026-2027.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent.tools import (
    GET_PROGRAM_REQUIREMENTS_TOOL,
    StudentContext,
    check_plan,
    get_program_requirements,
)
from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Student

YEAR = "2026-2027"


def course(code: str, catalog_year: str) -> dict:
    return {
        "code": code,
        "subject": code[:4],
        "number": code[4:],
        "title": f"Test course {code}",
        "credits": 3.0,
        "description": "Made-up course for tests.",
        "catalog_year": catalog_year,
    }


def program(program_id: str, degree_level: str, catalog_year: str, core: str) -> dict:
    return {
        "program_id": program_id,
        "name": f"Program {program_id}",
        "degree_level": degree_level,
        "catalog_year": catalog_year,
        "total_credits_required": 6,
        "requirement_groups": [{"group_id": "core", "label": "Core", "kind": "all", "courses": [core]}],
    }


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    courses = [course(code, year) for year in ("2025-2026", YEAR, "2027-2028") for code in ("TEST101", "TEST201")]
    programs = [
        program("t-bs", "bachelor", YEAR, "TEST101"),
        program("t-asi", "asi", "2025-2026", "TEST201"),
        program("old-bs", "bachelor", "2025-2026", "TEST101"),
        program("new-minor", "minor", "2027-2028", "TEST201"),
    ]
    (tmp_path / "data.json").write_text(json.dumps({"courses": courses, "programs": programs}))
    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)
    assert report.errors == {}
    return connection


def run_check(conn: sqlite3.Connection, programs: list[str], codes: list[str]) -> dict:
    student = Student(degree_level="bachelor", programs=programs, catalog_year=YEAR)
    context = StudentContext(student=student, overrides=frozenset())
    return check_plan(conn, {"semesters": [{"label": "Fall 2026", "courses": codes}]}, context)


def types(issues: list[dict]) -> set[str]:
    return {issue["type"] for issue in issues}


# --- check_plan ---------------------------------------------------------------------------------


def test_older_year_asi_is_checked_not_refused(conn: sqlite3.Connection) -> None:
    result = run_check(conn, ["t-bs", "t-asi"], ["TEST101"])
    assert "program_not_loaded" not in types(result["errors"])
    stale = [w["message"] for w in result["warnings"] if w["type"] == "stale_program_year"]
    assert len(stale) == 1 and "2025-2026" in stale[0]
    # Its requirements really are checked: TEST201 is missing from the ASI's core.
    assert any("Program t-asi: Core is missing TEST201" in e["message"] for e in result["errors"])


def test_older_year_asi_requirement_met_when_planned(conn: sqlite3.Connection) -> None:
    result = run_check(conn, ["t-bs", "t-asi"], ["TEST101", "TEST201"])
    assert not any("Program t-asi: Core" in e["message"] for e in result["errors"])


def test_older_year_degree_still_refused(conn: sqlite3.Connection) -> None:
    # The student's own degree never falls back (BUG-053's Expected).
    result = run_check(conn, ["old-bs"], ["TEST101"])
    assert "program_not_loaded" in types(result["errors"])
    assert "stale_program_year" not in types(result["warnings"])


def test_minor_only_in_a_later_year_is_still_refused(conn: sqlite3.Connection) -> None:
    # Never falls forward to a year after the student's.
    result = run_check(conn, ["t-bs", "new-minor"], ["TEST101"])
    assert "program_not_loaded" in types(result["errors"])


def test_malformed_stored_year_is_not_used(conn: sqlite3.Connection) -> None:
    # Only a hand-edited row can hold this (the loader refuses it, BUG-023a); it must neither be
    # planned against nor shown to the model.
    conn.execute("UPDATE programs SET catalog_year = '2025-2026 ' WHERE program_id = 't-asi'")
    result = run_check(conn, ["t-bs", "t-asi"], ["TEST101"])
    assert "program_not_loaded" in types(result["errors"])
    assert "2025-2026 " not in json.dumps(result)


# --- get_program_requirements -------------------------------------------------------------------


def test_requirements_fall_back_with_a_note(conn: sqlite3.Connection) -> None:
    result = get_program_requirements(conn, {"program_id": "t-asi", "catalog_year": YEAR})
    assert "error" not in result
    assert result["catalog_year"] == "2025-2026"
    assert result["requirement_groups"][0]["courses"] == ["TEST201"]
    assert "not in the 2026-2027 catalog data" in result["catalog_year_note"]
    assert "from the 2025-2026 catalog" in result["catalog_year_note"]


def test_requirements_in_the_asked_year_have_no_note(conn: sqlite3.Connection) -> None:
    assert "catalog_year_note" not in get_program_requirements(conn, {"program_id": "t-bs", "catalog_year": YEAR})


def test_requirements_without_a_year_have_no_note(conn: sqlite3.Connection) -> None:
    # Only one year is stored, so the lookup already picks it; nothing fell back.
    result = get_program_requirements(conn, {"program_id": "t-asi"})
    assert result["catalog_year"] == "2025-2026"
    assert "catalog_year_note" not in result


def test_requirements_for_an_older_year_degree_are_still_an_error(conn: sqlite3.Connection) -> None:
    result = get_program_requirements(conn, {"program_id": "old-bs", "catalog_year": YEAR})
    assert set(result) == {"error"}
    assert "exists only in catalog year 2025-2026" in result["error"]


def test_requirements_never_fall_forward(conn: sqlite3.Connection) -> None:
    result = get_program_requirements(conn, {"program_id": "new-minor", "catalog_year": YEAR})
    assert set(result) == {"error"}


def test_description_tells_the_model_to_plan_with_it() -> None:
    assert "catalog_year_note" in GET_PROGRAM_REQUIREMENTS_TOOL["description"]
