"""Plan store: save and load a student's plan (docs/plan-format.md) in SQLite."""

from __future__ import annotations

import sqlite3
import uuid

from degree_planner_backend.plan_models import Plan


class PlanNotFoundError(LookupError):
    """No plan with the given id."""


def save_plan(connection: sqlite3.Connection, plan: Plan) -> Plan:
    """Save a plan, assigning it a plan_id if it doesn't have one yet."""
    plan_id = plan.plan_id or str(uuid.uuid4())
    saved = plan.model_copy(update={"plan_id": plan_id})
    connection.execute(
        "INSERT OR REPLACE INTO plans (plan_id, data) VALUES (?, ?)",
        (plan_id, saved.model_dump_json(by_alias=True)),
    )
    connection.commit()
    return saved


def load_plan(connection: sqlite3.Connection, plan_id: str) -> Plan:
    row = connection.execute("SELECT data FROM plans WHERE plan_id = ?", (plan_id,)).fetchone()
    if row is None:
        raise PlanNotFoundError(f"no plan {plan_id!r}")
    return Plan.model_validate_json(row[0])
