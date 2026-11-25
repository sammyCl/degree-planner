import json
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from degree_planner_backend import main
from degree_planner_backend.agent.loop import ClaudeCodeError
from degree_planner_backend.agent.request_models import AgentResponse, Usage
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
    # BUG-049: CSCI400's unmet corequisite is now flagged too, alongside its unmet prerequisite.
    assert len(broken) == 2
    assert all(flag["course_id"] == "sem-2-csci400" for flag in broken)
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


def test_create_and_update_plan_never_trust_the_client_s_flags(client_with_catalog: TestClient) -> None:
    # POST /plans and PUT /plans/{plan_id} must re-run the validator before saving, the same as
    # POST /plans/check, or a client can forge a passing plan straight into the plan store.
    payload = json.loads((REPO_ROOT / "docs" / "plan-format.sample.json").read_text())
    payload["summary"]["requirements_met"] = True
    payload["flags"] = []

    created = client_with_catalog.post("/plans", json=payload)
    assert created.status_code == 200
    body = created.json()
    assert body["summary"]["requirements_met"] is False
    assert any(flag["type"] == "broken_prerequisite" for flag in body["flags"])

    plan_id = body["plan_id"]
    forged_update = {**payload, "summary": {**payload["summary"], "requirements_met": True}, "flags": []}
    updated = client_with_catalog.put(f"/plans/{plan_id}", json=forged_update)
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["summary"]["requirements_met"] is False
    assert any(flag["type"] == "broken_prerequisite" for flag in updated_body["flags"])

    fetched = client_with_catalog.get(f"/plans/{plan_id}")
    assert fetched.json()["summary"]["requirements_met"] is False


SETUP_REQUEST = {
    "student": {
        "degree_level": "bachelor",
        "programs": ["cs-bs-general-track"],
        "catalog_year": "2026-2027",
        "completed_courses": [],
    },
    "semesters": 8,
    "start_term": "Fall 2026",
}


def test_submit_setup_endpoint_returns_the_agent_s_response(
    client_with_catalog: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The agent loop itself (run_agent) has its own test suite (test_agent_loop.py); this only
    # checks the endpoint's wiring: it accepts an AgentRequest body and returns run_agent's
    # AgentResponse as JSON.
    canned = AgentResponse(
        status="cannot_work",
        plan=None,
        explanation="Could not fit every requirement in 8 semesters.",
        problems=("Math and Science needs 6.0 credits, only 0.0 completed or planned.",),
        usage=Usage(input_tokens=100, output_tokens=50, steps=3),
    )
    captured = {}

    def fake_run_agent(connection, request):
        captured["connection"] = connection
        captured["request"] = request
        return canned

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    response = client_with_catalog.post("/plans/submit-setup", json=SETUP_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cannot_work"
    assert body["plan"] is None
    assert body["problems"] == list(canned.problems)
    assert captured["request"].student.programs == ["cs-bs-general-track"]


def test_submit_setup_endpoint_returns_503_when_claude_code_is_unavailable(
    client_with_catalog: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run_agent(connection, request):
        raise ClaudeCodeError("'claude' is not installed or not on PATH")

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    response = client_with_catalog.post("/plans/submit-setup", json=SETUP_REQUEST)

    assert response.status_code == 503


def test_submit_setup_endpoint_rejects_a_malformed_request(client_with_catalog: TestClient) -> None:
    response = client_with_catalog.post("/plans/submit-setup", json={**SETUP_REQUEST, "semesters": 0})
    assert response.status_code == 422


def test_a_lone_surrogate_in_the_body_gets_422_not_500(client_with_empty_db: TestClient) -> None:
    # BUG-046: \ud800 is a lone surrogate, valid JSON but not valid text; FastAPI's default 422
    # handler used to echo it back and crash trying to encode the response as UTF-8.
    body = {
        "student": {"degree_level": "bachelor", "programs": ["x\ud800"], "catalog_year": "2026-2027"},
        "semesters": 5,
    }

    response = client_with_empty_db.post(
        "/plans/submit-setup", content=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_an_unexpected_error_is_a_clean_500_not_a_bare_crash(
    client_with_catalog: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Trial-ready API: a genuine bug or server problem we didn't anticipate (not an HTTPException
    # or a validation error, both handled elsewhere) should still reach the student as a normal,
    # readable response, with the real exception only in the server log.
    def fake_check_plan(connection, plan):
        raise RuntimeError("the database is locked")

    monkeypatch.setattr(main, "check_plan", fake_check_plan)

    # client_with_catalog's dependency override is on the shared `app`, so it still applies; a
    # plain TestClient(app) re-raises an unhandled exception instead of returning our 500 (so a
    # real bug stays loud in tests by default) — raise_server_exceptions=False shows what the
    # student's browser would actually get.
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/plans/check", json=json.loads(
        (REPO_ROOT / "docs" / "plan-format.sample.json").read_text()
    ))

    assert response.status_code == 500
    assert "locked" not in response.text
    assert response.json() == {"detail": "Something went wrong on our end. Please try again in a moment."}
