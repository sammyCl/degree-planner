import sqlite3

import pytest

from degree_planner_backend.db import init_schema
from degree_planner_backend.plan_models import Plan
from degree_planner_backend.plan_store import PlanNotFoundError, load_plan, save_plan

MINIMAL_PLAN = {
    "student": {
        "degree_level": "bachelor",
        "programs": ["cs-bs-general-track"],
        "catalog_year": "2026-2027",
        "completed_courses": [],
    },
    "semesters": [],
    "flags": [],
    "summary": {"total_credits": 0.0, "total_credits_required": 130.0, "requirements_met": False},
}


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def test_save_plan_assigns_an_id_when_missing(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate(MINIMAL_PLAN)
    assert plan.plan_id is None

    saved = save_plan(connection, plan)

    assert saved.plan_id is not None
    loaded = load_plan(connection, saved.plan_id)
    assert loaded.student.programs == ["cs-bs-general-track"]


def test_save_plan_keeps_an_existing_id(connection: sqlite3.Connection) -> None:
    plan = Plan.model_validate({**MINIMAL_PLAN, "plan_id": "plan-1"})

    saved = save_plan(connection, plan)

    assert saved.plan_id == "plan-1"


def test_save_plan_overwrites_on_the_same_id(connection: sqlite3.Connection) -> None:
    first = Plan.model_validate({**MINIMAL_PLAN, "plan_id": "plan-1"})
    save_plan(connection, first)

    second = Plan.model_validate(
        {
            **MINIMAL_PLAN,
            "plan_id": "plan-1",
            "student": {**MINIMAL_PLAN["student"], "programs": ["mining-bs"]},
        }
    )
    save_plan(connection, second)

    loaded = load_plan(connection, "plan-1")
    assert loaded.student.programs == ["mining-bs"]


def test_load_plan_missing_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(PlanNotFoundError):
        load_plan(connection, "no-such-plan")
