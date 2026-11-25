"""A minor/ASI/certificate not re-collected for the student's own catalog year falls back to its
own newest stored year no later than the student's, with a stale_program_year warning (frontend
request: Abdallah). The student's actual degree (bachelor's/master's/combined) never falls back."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, Semester, Student, Summary
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_program(program_id: str, degree_level: str, catalog_year: str, **extra: object) -> dict:
    return {
        "program_id": program_id,
        "name": extra.pop("name", program_id),
        "degree_level": degree_level,
        "catalog_year": catalog_year,
        "total_credits_required": 9,
        "requirement_groups": [{"group_id": "core", "label": "Core", "kind": "choose_credits", "credits_required": 3}],
    } | extra


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    programs = [
        make_program("t-bs", "bachelor", "2026-2027", total_credits_required=15),
        make_program("t-asi", "asi", "2025-2026", name="Old ASI"),
        make_program("t-asi", "asi", "2024-2025", name="Older ASI"),
        make_program("t-cert", "certificate", "2025-2026", name="Old Certificate"),
        make_program("t-future-asi", "asi", "2027-2028", name="Future ASI"),
        make_program("t-bs-old-only", "bachelor", "2025-2026", name="Old Bachelor's"),
    ]
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


def plan(programs: list[str]) -> Plan:
    return Plan(
        student=Student(degree_level="bachelor", programs=programs, catalog_year="2026-2027"),
        semesters=[Semester(semester_id="s1", label="S1", courses=[])],
        summary=Summary(total_credits=0, total_credits_required=0, requirements_met=False),
    )


def stale_year_flags(checked: Plan) -> list[str]:
    return [f.message for f in checked.flags if f.type == "stale_program_year"]


def test_asi_falls_back_to_its_newest_earlier_year(connection: sqlite3.Connection) -> None:
    checked = check_plan(connection, plan(["t-bs", "t-asi"]))
    (message,) = stale_year_flags(checked)
    assert message.startswith("Old ASI is not in the 2026-2027 catalog data")
    assert "2025-2026" in message
    # The ASI's own requirement group is still checked (it was actually loaded, not just flagged).
    assert any(status.program_id == "t-asi" for status in checked.requirement_status)


def test_falls_back_to_the_newest_of_several_earlier_years_not_the_oldest(connection: sqlite3.Connection) -> None:
    # t-asi is stored for both 2024-2025 and 2025-2026; 2025-2026 (the newer one) should win.
    checked = check_plan(connection, plan(["t-bs", "t-asi"]))
    (message,) = stale_year_flags(checked)
    assert "2025-2026" in message and "2024-2025" not in message


def test_certificate_gets_the_same_fallback_as_minor_and_asi(connection: sqlite3.Connection) -> None:
    checked = check_plan(connection, plan(["t-bs", "t-cert"]))
    (message,) = stale_year_flags(checked)
    assert message.startswith("Old Certificate is not in the 2026-2027 catalog data")


def test_never_falls_forward_to_a_later_year(connection: sqlite3.Connection) -> None:
    # t-future-asi only exists for 2027-2028 (later than the student's 2026-2027): no fallback,
    # same silent-drop as before this feature existed, not a flag claiming a year that hasn't
    # happened yet.
    checked = check_plan(connection, plan(["t-bs", "t-future-asi"]))
    assert stale_year_flags(checked) == []
    assert not any(status.program_id == "t-future-asi" for status in checked.requirement_status)


def test_the_students_own_degree_never_falls_back(connection: sqlite3.Connection) -> None:
    # t-bs-old-only is a bachelor's program, not an add-on: a missing degree program is a much
    # bigger deal than a missing minor, so this keeps today's silent-drop rather than quietly
    # substituting an old year for the student's actual degree.
    checked = check_plan(connection, plan(["t-bs-old-only"]))
    assert stale_year_flags(checked) == []
    assert not any(status.program_id == "t-bs-old-only" for status in checked.requirement_status)


def test_real_asi_data_falls_back_from_2026_2027() -> None:
    # Every real ASI is currently stored only for 2025-2026 (CONFLICT-LOG.md); a 2026-2027 student
    # choosing one used to have it silently dropped from the plan with no requirements checked at
    # all. Confirms the fallback also works against the real, unmodified data/json/.
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    checked = check_plan(conn, plan(["cs-bs-general-track", "aerospace-engineering-asi"]))
    (message,) = stale_year_flags(checked)
    assert "aerospace-engineering-asi" not in message  # the program's name is shown, not its id
    assert "2025-2026" in message
    assert any(status.program_id == "aerospace-engineering-asi" for status in checked.requirement_status)
