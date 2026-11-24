"""Tests for the try-chat command (agent/try_chat.py). run_chat is replaced, so no model runs."""

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent import chat_loop, loop, try_chat
from degree_planner_backend.agent.chat_models import ChatResponse, PlanChange
from degree_planner_backend.agent.request_models import Override, Usage
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary

STUDENT = {"degree_level": "bachelor", "programs": ["tiny-bs"], "catalog_year": "2026-2027"}


def course(code: str) -> PlannedCourse:
    return PlannedCourse(course_id=f"c-{code}", code=code, title=code, credits=3.0, status="planned")


def plan(fall: list[str], spring: list[str]) -> Plan:
    return Plan(
        student=Student(**STUDENT),
        semesters=[
            Semester(semester_id="s1", label="Fall 2026", courses=[course(c) for c in fall], total_credits=3.0 * len(fall)),
            Semester(semester_id="s2", label="Spring 2027", courses=[course(c) for c in spring],
                     total_credits=3.0 * len(spring)),
        ],
        flags=[],
        summary=Summary(total_credits=3.0 * (len(fall) + len(spring)), total_credits_required=6.0,
                        requirements_met=False),
    )


REQUEST = {
    "plan": json.loads(plan(["TEST101", "TEST201"], []).model_dump_json(by_alias=True)),
    "overrides": [],
    "messages": [{"role": "student", "text": "Can TEST201 wait until spring?"}],
}

PROPOSAL = ChatResponse(
    reply="I propose moving TEST201 to Spring 2027.",
    proposed_plan=plan(["TEST101"], ["TEST201"]),
    changes=(PlanChange(kind="move", code="TEST201", from_label="Fall 2026", to_label="Spring 2027"),),
    accepted_overrides=(Override(type="exception_claimed", code="TEST101"),),
    still_open=("Core is missing TEST102.",),
    usage=Usage(input_tokens=2000, output_tokens=300, steps=4),
)
ANSWER = ChatResponse(reply="Which elective do you mean?", usage=Usage(input_tokens=50, output_tokens=5, steps=2))
STOPPED = ChatResponse(reply=chat_loop.STOPPED_REPLY, problems=(chat_loop.STEP_LIMIT_PROBLEM,),
                       usage=Usage(input_tokens=10, output_tokens=2, steps=12))


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    request = tmp_path / "request.json"
    request.write_text(json.dumps(REQUEST))
    db = tmp_path / "catalog.db"
    sqlite3.connect(db).close()
    return request, db


def fake_run_chat(response: ChatResponse, seen: list | None = None):
    def run(connection, request, runner=None, trace=None):
        if seen is not None:
            seen.append(request)
        return response
    return run


def test_prints_a_proposal(files, monkeypatch, capsys) -> None:
    request, db = files
    seen: list = []
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(PROPOSAL, seen))

    assert try_chat.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert seen[0].semester_labels() == ["Fall 2026", "Spring 2027"]
    assert "student: Can TEST201 wait until spring?" in out
    assert f"steps: 4 of {chat_loop.CHAT_STEP_LIMIT}" in out
    assert "tokens: 2000 in, 300 out" in out
    assert "changes:\n  move TEST201 Fall 2026 -> Spring 2027" in out
    assert "accepted exceptions: TEST101" in out
    assert "still open:\n  - Core is missing TEST102." in out
    assert "proposed plan: 6 of 6 credits, requirements met: no" in out
    assert "  Fall 2026 (3 cr): TEST101" in out
    assert "  Spring 2027 (3 cr): TEST201" in out
    assert out.rstrip().endswith("I propose moving TEST201 to Spring 2027.")


def test_prints_an_answer_without_a_proposal(files, monkeypatch, capsys) -> None:
    request, db = files
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(ANSWER))

    assert try_chat.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "changes: none" in out
    assert "accepted exceptions: none" in out
    assert "still open" not in out
    assert "proposed plan: none" in out
    assert out.rstrip().endswith("Which elective do you mean?")


def test_prints_problems(files, monkeypatch, capsys) -> None:
    request, db = files
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(STOPPED))

    assert try_chat.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert f"steps: 12 of {chat_loop.CHAT_STEP_LIMIT}" in out
    assert f"problems:\n  - {chat_loop.STEP_LIMIT_PROBLEM}" in out


def test_say_replaces_the_last_student_message(files, monkeypatch) -> None:
    request, db = files
    seen: list = []
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(ANSWER, seen))

    assert try_chat.main([str(request), "--db", str(db), "--say", "Swap my elective."]) == 0
    assert [(m.role, m.text) for m in seen[0].messages] == [("student", "Swap my elective.")]


def test_say_follows_an_assistant_message(files, monkeypatch) -> None:
    request, db = files
    messages = REQUEST["messages"] + [{"role": "assistant", "text": "Which semester?"}]
    request.write_text(json.dumps(REQUEST | {"messages": messages}))
    seen: list = []
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(ANSWER, seen))

    assert try_chat.main([str(request), "--db", str(db), "--say", "Spring 2027."]) == 0
    assert [m.role for m in seen[0].messages] == ["student", "assistant", "student"]
    assert seen[0].messages[-1].text == "Spring 2027."


def test_a_file_ending_with_the_assistant_needs_say(files, capsys) -> None:
    request, db = files
    messages = REQUEST["messages"] + [{"role": "assistant", "text": "Which semester?"}]
    request.write_text(json.dumps(REQUEST | {"messages": messages}))

    assert try_chat.main([str(request), "--db", str(db)]) == 2
    assert "the last message must be the student's" in capsys.readouterr().err


def test_saves_the_full_response(files, monkeypatch, tmp_path) -> None:
    request, db = files
    monkeypatch.setattr(chat_loop, "run_chat", fake_run_chat(PROPOSAL))
    out_file = tmp_path / "response.json"

    assert try_chat.main([str(request), "--db", str(db), "--json", str(out_file)]) == 0
    assert ChatResponse.model_validate_json(out_file.read_text()) == PROPOSAL


def test_missing_request_file(tmp_path, capsys) -> None:
    assert try_chat.main([str(tmp_path / "nope.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_request_that_is_not_json(files, capsys) -> None:
    request, db = files
    request.write_text("{not json")

    assert try_chat.main([str(request), "--db", str(db)]) == 2
    assert "not a valid chat request" in capsys.readouterr().err


def test_invalid_request(files, capsys) -> None:
    request, db = files
    request.write_text(json.dumps(REQUEST | {"extra": 1}))

    assert try_chat.main([str(request), "--db", str(db)]) == 2
    assert "not a valid chat request" in capsys.readouterr().err


def test_missing_database(files, tmp_path, capsys) -> None:
    request, _ = files
    assert try_chat.main([str(request), "--db", str(tmp_path / "none.db")]) == 2
    assert "load-data" in capsys.readouterr().err


def test_claude_code_not_available(files, monkeypatch, capsys) -> None:
    request, db = files

    def broken(connection, request, runner=None, trace=None):
        raise loop.ClaudeCodeError("'claude' is not installed or not on PATH")

    monkeypatch.setattr(chat_loop, "run_chat", broken)
    assert try_chat.main([str(request), "--db", str(db)]) == 1
    assert "signed in" in capsys.readouterr().err


def test_database_is_opened_read_only(files, monkeypatch) -> None:
    request, db = files

    def writes(connection, request, runner=None, trace=None):
        connection.execute("CREATE TABLE t (x)")

    monkeypatch.setattr(chat_loop, "run_chat", writes)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        try_chat.main([str(request), "--db", str(db)])


def test_prints_the_tool_calls(files, monkeypatch, capsys) -> None:
    request, db = files

    def run(connection, request, runner=None, trace=None):
        trace.extend([
            {"tool": "get_prerequisites", "input": '{"code": "CSCI403"}', "ok": True, "error": None},
            {"tool": "replace_course", "input": '{"old_code": "CSCI400"}', "ok": False, "error": "Not changed: x"},
        ])
        return ANSWER

    monkeypatch.setattr(chat_loop, "run_chat", run)
    assert try_chat.main([str(request), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "tool calls (2):" in out
    assert '1. get_prerequisites {"code": "CSCI403"} -> ok' in out
    assert "2. replace_course" in out and "-> error: Not changed: x" in out
