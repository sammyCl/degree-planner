import json
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.db import get_db, init_schema
from degree_planner_backend.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def _override_with(connection: sqlite3.Connection):
    def override() -> Iterator[sqlite3.Connection]:
        yield connection

    return override


@pytest.fixture
def client_with_catalog(tmp_path: Path) -> Iterator[TestClient]:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "sample.json")
    # TestClient runs the endpoint in a worker thread, but this fixture creates the
    # connection on the test thread, so the in-memory db must allow cross-thread use.
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    refresh_database(tmp_path, connection)

    app.dependency_overrides[get_db] = _override_with(connection)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()


@pytest.fixture
def client_with_empty_db() -> Iterator[TestClient]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(connection)

    app.dependency_overrides[get_db] = _override_with(connection)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()


def test_check_plan_endpoint_flags_broken_prerequisite(client_with_catalog: TestClient) -> None:
    payload = json.loads((REPO_ROOT / "docs" / "plan-format.sample.json").read_text())

    response = client_with_catalog.post("/plans/check", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["requirements_met"] is False
    broken = [flag for flag in body["flags"] if flag["type"] == "broken_prerequisite"]
    assert len(broken) == 1
    assert broken[0]["course_id"] == "sem-2-csci400"
    assert {"from": "sem-1-csci200", "to": "sem-2-csci306"} in body["prerequisite_edges"]


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


def test_plan_store_round_trip(client_with_empty_db: TestClient) -> None:
    created = client_with_empty_db.post("/plans", json=MINIMAL_PLAN)
    assert created.status_code == 200
    plan_id = created.json()["plan_id"]
    assert plan_id

    fetched = client_with_empty_db.get(f"/plans/{plan_id}")
    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == plan_id

    updated_payload = {**MINIMAL_PLAN, "student": {**MINIMAL_PLAN["student"], "programs": ["mining-bs"]}}
    updated = client_with_empty_db.put(f"/plans/{plan_id}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["plan_id"] == plan_id
    assert updated.json()["student"]["programs"] == ["mining-bs"]

    refetched = client_with_empty_db.get(f"/plans/{plan_id}")
    assert refetched.json()["student"]["programs"] == ["mining-bs"]


def test_get_missing_plan_returns_404(client_with_empty_db: TestClient) -> None:
    response = client_with_empty_db.get("/plans/no-such-plan")
    assert response.status_code == 404
