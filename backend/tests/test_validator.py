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
    # BUG-025: Core (CSCI200, CSCI306, CSCI400) claims those courses first, so Free Electives
    # (no course list) can no longer double-count them; it now falls short too.
    assert len(shortfalls) == 3  # Math and Science, Free Electives, and the overall total
    assert {"Math and Science", "Free Electives"} <= {
        flag.message.split(": ", 1)[1].split(" needs", 1)[0] for flag in shortfalls if ": " in flag.message
    }

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


def test_check_plan_does_not_let_free_electives_recount_a_fixed_group_s_courses(tmp_path: Path) -> None:
    # BUG-025: a course already used to satisfy an "all" group must not also count toward a
    # choose_credits group (e.g. free electives) in the same program.
    (tmp_path / "program.json").write_text(
        json.dumps(
            {
                "courses": [
                    {"code": "X100", "subject": "X", "number": "100", "title": "X100", "credits": 3.0,
                     "description": "", "prerequisites": None, "catalog_year": "2099-2000"},
                    {"code": "X200", "subject": "X", "number": "200", "title": "X200", "credits": 3.0,
                     "description": "", "prerequisites": None, "catalog_year": "2099-2000"},
                ],
                "programs": [
                    {
                        "program_id": "prog-core-free",
                        "name": "Core and Free Electives Program",
                        "degree_level": "bachelor",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 0,
                        "requirement_groups": [
                            {"group_id": "core", "label": "Core", "kind": "all", "courses": ["X100", "X200"]},
                            {"group_id": "free", "label": "Free Electives", "kind": "choose_credits", "credits_required": 6},
                        ],
                    }
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
                "programs": ["prog-core-free"],
                "catalog_year": "2099-2000",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Term 1",
                    "courses": [
                        {"course_id": "sem-1-x100", "code": "X100", "title": "X100", "credits": 3.0, "status": "planned"},
                        {"course_id": "sem-1-x200", "code": "X200", "title": "X200", "credits": 3.0, "status": "planned"},
                    ],
                    "total_credits": 0.0,
                }
            ],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    assert not [flag for flag in result.flags if flag.type == "requirement_unmet"]  # Core is satisfied
    shortfalls = [flag for flag in result.flags if flag.type == "credit_shortfall"]
    assert len(shortfalls) == 1
    assert "Free Electives" in shortfalls[0].message
    assert "only 0.0" in shortfalls[0].message


def test_check_plan_lets_a_shared_candidate_satisfy_only_one_choose_credits_group(tmp_path: Path) -> None:
    # BUG-025's second case: two choose_credits groups that both list the same course must not
    # both be satisfied by that one course; the first group (declared first) claims it.
    (tmp_path / "program.json").write_text(
        json.dumps(
            {
                "courses": [
                    {"code": "MATH201", "subject": "MATH", "number": "201", "title": "Stats", "credits": 3.0,
                     "description": "", "prerequisites": None, "catalog_year": "2099-2000"},
                    {"code": "CSCI100", "subject": "CSCI", "number": "100", "title": "CS100", "credits": 3.0,
                     "description": "", "prerequisites": None, "catalog_year": "2099-2000"},
                    {"code": "CSCI200", "subject": "CSCI", "number": "200", "title": "CS200", "credits": 3.0,
                     "description": "", "prerequisites": None, "catalog_year": "2099-2000"},
                ],
                "programs": [
                    {
                        "program_id": "prog-ab",
                        "name": "A/B Program",
                        "degree_level": "bachelor",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 0,
                        "requirement_groups": [
                            {"group_id": "a", "label": "Group A", "kind": "choose_credits",
                             "courses": ["MATH201", "CSCI100"], "credits_required": 3},
                            {"group_id": "b", "label": "Group B", "kind": "choose_credits",
                             "courses": ["MATH201", "CSCI200"], "credits_required": 3},
                        ],
                    }
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
                "programs": ["prog-ab"],
                "catalog_year": "2099-2000",
                "completed_courses": [],
            },
            "semesters": [
                {
                    "semester_id": "sem-1",
                    "label": "Term 1",
                    "courses": [
                        {"course_id": "sem-1-math201", "code": "MATH201", "title": "Stats", "credits": 3.0, "status": "planned"},
                    ],
                    "total_credits": 0.0,
                }
            ],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    shortfalls = [flag for flag in result.flags if flag.type == "credit_shortfall"]
    assert len(shortfalls) == 1
    assert "Group B" in shortfalls[0].message  # Group A (declared first) claims MATH201


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


def test_check_plan_rejects_a_forged_override_on_a_non_overridable_flag(connection: sqlite3.Connection) -> None:
    # BUG-024 / BUG-032: only overridable flags (exception_claimed) may carry overridden
    # forward; a forged override on an error flag like broken_prerequisite or
    # credit_shortfall must not make the plan pass.
    plan = Plan.model_validate(json.loads((REPO_ROOT / "docs" / "plan-format.sample.json").read_text()))

    first = check_plan(connection, plan)
    assert first.summary.requirements_met is False

    forged = first.model_copy(deep=True)
    for flag in forged.flags:
        flag.overridden = True
    assert any(flag.type in ("broken_prerequisite", "credit_shortfall") for flag in forged.flags)

    second = check_plan(connection, forged)

    for flag in second.flags:
        if flag.type in ("broken_prerequisite", "credit_shortfall"):
            assert flag.overridden is False
    assert second.summary.requirements_met is False


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


def test_check_plan_ignores_an_unknown_program_instead_of_crashing(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(
        {
            "student": {
                "degree_level": "bachelor",
                "programs": ["no-such-program"],
                "catalog_year": "2026-2027",
                "completed_courses": [],
            },
            "semesters": [],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    assert result.summary.total_credits_required == 0.0
    assert not [flag for flag in result.flags if flag.type == "requirement_unmet"]


def test_check_plan_ignores_a_combined_program_s_unloaded_component(tmp_path: Path) -> None:
    (tmp_path / "combined.json").write_text(
        json.dumps(
            {
                "programs": [
                    {
                        "program_id": "combo",
                        "name": "Combo",
                        "degree_level": "combined",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 10,
                        "requirement_groups": [],
                        # "component-bs" is never loaded: the component data hasn't landed yet.
                        "combines": ["component-bs", "component-ms"],
                    },
                    {
                        "program_id": "component-ms",
                        "name": "Component MS",
                        "degree_level": "master",
                        "catalog_year": "2099-2000",
                        "total_credits_required": 10,
                        "requirement_groups": [
                            {"group_id": "core", "label": "Core", "kind": "all", "courses": []}
                        ],
                    },
                ]
            }
        )
    )
    connection = sqlite3.connect(":memory:")
    refresh_database(tmp_path, connection)

    plan = Plan.model_validate(
        {
            "student": {
                "degree_level": "combined",
                "programs": ["combo"],
                "catalog_year": "2099-2000",
                "completed_courses": [],
            },
            "semesters": [],
            "flags": [],
            "summary": {"total_credits": 0.0, "total_credits_required": 0.0, "requirements_met": False},
        }
    )

    result = check_plan(connection, plan)

    # The loaded component (component-ms) is still checked; the missing one is skipped, not a crash.
    assert result.summary.total_credits_required == 10.0
    assert not [flag for flag in result.flags if flag.type == "requirement_unmet"]
