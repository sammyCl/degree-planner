"""Tests for the try-agent command (agent/try_agent.py). run_agent is replaced, so no model runs."""

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent import loop, try_agent
from degree_planner_backend.agent.request_models import AgentResponse, Usage
from degree_planner_backend.plan_models import Flag, Plan, PlannedCourse, Semester, Student, Summary

REQUEST = {
    "student": {"degree_level": "bachelor", "programs": ["tiny-bs"], "catalog_year": "2026-2027"},
    "semesters": 2,
    "start_term": "Fall 2026",
}


def course(code: str) -> PlannedCourse:
    return PlannedCourse(course_id=f"c-{code}", code=code, title=code, credits=3.0, status="planned")


def plan(met: bool) -> Plan:
    return Plan(
        student=Student(**REQUEST["student"]),
        semesters=[
            Semester(semester_id="s1", label="Fall 2026", courses=[course("TEST101")], total_credits=3.0),
            Semester(semester_id="s2", label="Spring 2027", courses=[] if not met else [course("TEST102")],
                     total_credits=0.0 if not met else 3.0),
        ],
        flags=[] if met else [Flag(flag_id="f1", type="requirement_unmet", severity="error", course_id=None,
                                   message="Core is missing TEST102.", overridable=False)],
        summary=Summary(total_credits=6.0 if met else 3.0, total_credits_required=6.0, requirements_met=met),
    )


OK = AgentResponse(status="ok", plan=plan(True), explanation="TEST101, then TEST102.",
                   usage=Usage(input_tokens=2000, output_tokens=300, steps=5))
NOT_OK = AgentResponse(status="cannot_work", plan=plan(False), explanation="Could not fit TEST102.",
                       problems=("Core is missing TEST102.",), usage=Usage(input_tokens=10, output_tokens=2, steps=1))


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    request = tmp_path / "request.json"
    request.write_text(json.dumps(REQUEST))
    db = tmp_path / "catalog.db"
    sqlite3.connect(db).close()
    return request, db


def fake_run_agent(response: AgentResponse, seen: list | None = None):
    def run(connection, request):
        if seen is not None:
            seen.append(request)
        return response
    return run


def test_prints_the_summary(files, monkeypatch, capsys) -> None:
    request, db = files
    seen: list = []
    monkeypatch.setattr(loop, "run_agent", fake_run_agent(OK, seen))

    assert try_agent.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert seen[0].semester_labels() == ["Fall 2026", "Spring 2027"]
    assert "status: ok" in out
    assert f"steps: 5 of {loop.STEP_LIMIT}" in out
    assert "tokens: 2000 in, 300 out" in out
    assert "plan: 6 of 6 credits, requirements met: yes" in out
    assert "  Fall 2026 (3 cr): TEST101" in out
    assert "  Spring 2027 (3 cr): TEST102" in out
    assert out.rstrip().endswith("TEST101, then TEST102.")


def test_prints_problems_and_open_flags(files, monkeypatch, capsys) -> None:
    request, db = files
    monkeypatch.setattr(loop, "run_agent", fake_run_agent(NOT_OK))

    assert try_agent.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "status: cannot_work" in out
    assert "problems:\n  - Core is missing TEST102." in out
    assert "  Spring 2027 (0 cr): (none)" in out
    assert "flags:\n  - [error] Core is missing TEST102." in out


def test_saves_the_full_response(files, monkeypatch, tmp_path) -> None:
    request, db = files
    monkeypatch.setattr(loop, "run_agent", fake_run_agent(OK))
    out_file = tmp_path / "response.json"

    assert try_agent.main([str(request), "--db", str(db), "--json", str(out_file)]) == 0
    assert AgentResponse.model_validate_json(out_file.read_text()) == OK


def test_missing_request_file(tmp_path, capsys) -> None:
    assert try_agent.main([str(tmp_path / "nope.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_request(files, capsys) -> None:
    request, db = files
    request.write_text(json.dumps(REQUEST | {"semesters": "8"}))

    assert try_agent.main([str(request), "--db", str(db)]) == 2
    assert "not a valid agent request" in capsys.readouterr().err


def test_missing_database(files, tmp_path, capsys) -> None:
    request, _ = files
    assert try_agent.main([str(request), "--db", str(tmp_path / "none.db")]) == 2
    assert "load-data" in capsys.readouterr().err


def test_claude_code_not_available(files, monkeypatch, capsys) -> None:
    request, db = files

    def broken(connection, request):
        raise loop.ClaudeCodeError("'claude' is not installed or not on PATH")

    monkeypatch.setattr(loop, "run_agent", broken)
    assert try_agent.main([str(request), "--db", str(db)]) == 1
    assert "signed in" in capsys.readouterr().err


def test_database_is_opened_read_only(files, monkeypatch) -> None:
    request, db = files

    def writes(connection, request):
        connection.execute("CREATE TABLE t (x)")

    monkeypatch.setattr(loop, "run_agent", writes)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        try_agent.main([str(request), "--db", str(db)])
