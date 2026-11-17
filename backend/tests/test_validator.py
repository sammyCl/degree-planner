import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan
from degree_planner_backend.validator import check_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "sample.json")
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def _edge_pairs(plan: Plan) -> set[tuple[str, str]]:
    return {(edge.from_, edge.to) for edge in plan.prerequisite_edges}


def test_check_plan_matches_the_sample_plan(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(json.loads((REPO_ROOT / "docs" / "plan-format.sample.json").read_text()))

    result = check_plan(connection, plan)

    assert _edge_pairs(result) == {("sem-1-csci200", "sem-2-csci306"), ("sem-2-csci306", "sem-2-csci400")}

    broken = [flag for flag in result.flags if flag.type == "broken_prerequisite"]
    assert len(broken) == 1
    assert broken[0].course_id == "sem-2-csci400"
    assert broken[0].severity == "error"
    assert "CSCI306 and (MATH201 or MATH223)" in broken[0].message

    shortfalls = [flag for flag in result.flags if flag.type == "credit_shortfall"]
    assert len(shortfalls) == 2  # the unmet Math and Science group, and the overall total

    assert result.summary.total_credits == 14.0
    assert result.summary.total_credits_required == 130.0
    assert result.summary.requirements_met is False

    # the backend recomputes each semester's total, never trusting the input
    assert result.semesters[0].total_credits == 4.0
    assert result.semesters[1].total_credits == 6.0


def test_check_plan_flags_claimed_exception_and_checks_combined_requirements(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(
        {
            "plan_id": None,
            "student": {
                "degree_level": "combined",
                "programs": ["mining-bs-ms-combined"],
                "catalog_year": "2026-2027",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Fall 2026",
                    "courses": [
                        {
                            "course_id": "sem-1-mngn501",
                            "code": "MNGN501",
                            "title": "Advanced Mine Design",
                            "credits": 3.0,
                            "status": "planned",
                        },
                        {
                            "course_id": "sem-1-mngn502",
                            "code": "MNGN502",
                            "title": "Rock Mechanics for Mine Design",
                            "credits": 3.0,
                            "status": "planned",
                        },
                    ],
                    "total_credits": 0.0,
                }
            ],
            "prerequisite_edges": [],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    exceptions = [flag for flag in result.flags if flag.type == "exception_claimed"]
    assert len(exceptions) == 1
    assert exceptions[0].course_id == "sem-1-mngn501"
    assert exceptions[0].severity == "warning"
    assert exceptions[0].overridable is True

    # mining-bs's and mining-ms's "all" requirement groups are both satisfied; no requirement_unmet
    assert not [flag for flag in result.flags if flag.type == "requirement_unmet"]
    # 3 shared credits is within mining-ms's 12-credit double-count cap with mining-bs
    assert not [flag for flag in result.flags if flag.type == "double_count_exceeded"]
    # MNGN501's only prerequisite is the claimed exception, so it draws no edge
    assert result.prerequisite_edges == []

    assert result.summary.total_credits == 6.0
    assert result.summary.total_credits_required == 164.0
    assert result.summary.requirements_met is False  # short of the combined 164 credits


def test_check_plan_flags_double_count_over_the_cap(tmp_path: Path) -> None:
    (tmp_path / "shared.json").write_text(
        json.dumps(
            {
                "courses": [
                    {
                        "code": "X100",
                        "subject": "X",
                        "number": "100",
                        "title": "Shared Course",
                        "credits": 3.0,
                        "description": "",
                        "prerequisites": None,
                        "catalog_year": "2099-2000",
                    }
                ],
                "programs": [
                    {
                        "program_id": "prog-a",
                        "name": "Program A",
                        "degree_level": "bachelor",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 0,
                        "requirement_groups": [],
                        "double_counts_with": [
                            {"program_id": "prog-b", "shared_courses": ["X100"], "shared_credit_limit": 2}
                        ],
                    },
                    {
                        "program_id": "prog-b",
                        "name": "Program B",
                        "degree_level": "bachelor",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 0,
                        "requirement_groups": [],
                    },
                ],
            }
        )
    )
    connection = sqlite3.connect(":memory:")
    refresh_database(tmp_path, connection)

    plan = Plan.model_validate(
        {
            "student": {
                "degree_level": "bachelor",
                "programs": ["prog-a"],
                "catalog_year": "2099-2000",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Term 1",
                    "courses": [
                        {"course_id": "sem-1-x100", "code": "X100", "title": "Shared Course", "credits": 3.0, "status": "planned"}
                    ],
                    "total_credits": 0.0,
                }
            ],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    double_counts = [flag for flag in result.flags if flag.type == "double_count_exceeded"]
    assert len(double_counts) == 1
    assert "3.0 credits" in double_counts[0].message
    assert "2" in double_counts[0].message


def test_check_plan_preserves_overridden_flags_across_revalidation(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(
        {
            "student": {
                "degree_level": "master",
                "programs": ["mining-ms"],
                "catalog_year": "2026-2027",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Fall 2026",
                    "courses": [
                        {
                            "course_id": "sem-1-mngn501",
                            "code": "MNGN501",
                            "title": "Advanced Mine Design",
                            "credits": 3.0,
                            "status": "planned",
                        },
                        {
                            "course_id": "sem-1-mngn502",
                            "code": "MNGN502",
                            "title": "Rock Mechanics for Mine Design",
                            "credits": 3.0,
                            "status": "planned",
                        },
                    ],
                    "total_credits": 0.0,
                }
            ],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    first = check_plan(connection, plan)
    exception_flag = next(flag for flag in first.flags if flag.type == "exception_claimed")
    assert exception_flag.overridden is False

    exception_flag.overridden = True
    second = check_plan(connection, first)

    exception_flag_again = next(flag for flag in second.flags if flag.type == "exception_claimed")
    assert exception_flag_again.overridden is True


def test_check_plan_ignores_unknown_courses_instead_of_crashing(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(
        {
            "student": {
                "degree_level": "bachelor",
                "programs": ["cs-bs-general-track"],
                "catalog_year": "2026-2027",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Fall 2026",
                    "courses": [
                        {"course_id": "sem-1-unk", "code": "UNKNOWN999", "title": "Unknown", "credits": 3.0, "status": "planned"}
                    ],
                    "total_credits": 0.0,
                }
            ],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    assert not [flag for flag in result.flags if flag.type == "broken_prerequisite"]
