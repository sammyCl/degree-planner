"""Tests for POST /plans/chat. The chat loop itself has its own tests (test_chat_loop.py); these only
check the endpoint's wiring, with run_chat replaced: no model, no login."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from degree_planner_backend import main
from degree_planner_backend.agent.chat_models import ChatResponse
from degree_planner_backend.agent.loop import ClaudeCodeError
from degree_planner_backend.db import get_db
from degree_planner_backend.main import app

DOCS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture
def client() -> Iterator[TestClient]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    app.dependency_overrides[get_db] = lambda: connection
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()


def sample_request() -> dict:
    return json.loads((DOCS / "chat-request.sample.json").read_text())


def test_chat_returns_the_loop_s_response(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = ChatResponse.model_validate_json((DOCS / "chat-response.sample.json").read_text())
    seen = {}

    def fake_run_chat(connection, request):
        seen["text"] = request.messages[-1].text
        return expected

    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    response = client.post("/plans/chat", json=sample_request())

    assert response.status_code == 200
    assert response.json() == json.loads(expected.model_dump_json(by_alias=True))
    assert "from" in response.json()["proposed_plan"]["prerequisite_edges"][0]
    assert seen["text"] == sample_request()["messages"][-1]["text"]


def test_chat_rejects_a_bad_request(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_chat", lambda connection, request: pytest.fail("run_chat must not be called"))
    body = sample_request()
    body["messages"].append({"role": "assistant", "text": "Last word."})

    assert client.post("/plans/chat", json=body).status_code == 422


def test_chat_returns_503_when_claude_code_cannot_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_claude(connection, request):
        raise ClaudeCodeError("'claude' is not installed or not on PATH")

    monkeypatch.setattr(main, "run_chat", no_claude)
    response = client.post("/plans/chat", json=sample_request())

    assert response.status_code == 503
    assert "not installed" in response.json()["detail"]
