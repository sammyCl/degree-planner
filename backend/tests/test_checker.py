"""Tests for agent/checker.py, the eval's adversarial checker (agent/eval: Samantha). A fake runner
stands in for `claude -p`, so nothing here calls a model or the web."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent import checker
from degree_planner_backend.agent.agent_file import AgentFileError, parse_agent
from degree_planner_backend.agent.eval_checks import load_examples
from degree_planner_backend.agent.loop import ClaudeRun
from degree_planner_backend.agent.request_models import AgentResponse, Usage
from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Summary

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    return conn


@pytest.fixture(scope="module")
def ex2():
    return next(e for e in load_examples() if e.id == 2)


def plan_response(example, status: str = "ok") -> AgentResponse:
    labels = example.request.semester_labels()
    semesters = [
        Semester(semester_id=f"s{i}", label=label, total_credits=6.0, courses=[
            PlannedCourse(course_id=f"c{i}a", code="EENG500", title="Graduate Seminar", credits=0.0, status="planned"),
            PlannedCourse(course_id=f"c{i}b", code="EENG525", title="Antennas", credits=3.0, status="planned"),
        ])
        for i, label in enumerate(labels)
    ]
    plan = Plan(student=example.request.student, semesters=semesters,
                summary=Summary(total_credits=30, total_credits_required=30, requirements_met=True))
    return AgentResponse(status=status, plan=plan, explanation="x", problems=() if status == "ok" else ("p",),
                         usage=Usage(input_tokens=1, output_tokens=1, steps=1))


GOOD_PAGE = "https://catalog.mines.edu/graduate/programs/electricalengineering/"
BLOCKING = {"severity": "blocking", "claim": "EENG525 is only 3 of the 12 core credits", "url": GOOD_PAGE,
            "quote": "12 credits of core courses"}
CONCERN = {"severity": "concern", "claim": "transfer needs a Degree Audit form", "url": "", "quote": ""}


def answer(verdict: str, findings: list[dict], pages: list[str] | None = None, *, where: str = "structured_output",
           **result: object) -> ClaudeRun:
    body = {"verdict": verdict, "summary": "s", "findings": findings, "pages_read": [GOOD_PAGE] if pages is None else pages}
    out = {"subtype": "success", "is_error": False, "num_turns": 7,
           "usage": {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 20}} | result
    if where == "structured_output":
        out["structured_output"] = body
    else:
        out["result"] = json.dumps(body)
    return ClaudeRun(result=out)


# ------------------------------------------------------------------------------- the command

def test_checker_md_loads_with_webfetch_only() -> None:
    assert checker.AGENT.tools == ("WebFetch",)
    assert checker.AGENT.name == "checker"


def test_agent_file_still_rejects_tools_the_agent_cannot_use() -> None:
    text = "---\nname: x\nmodel: m\neffort: low\nmaxTurns: 3\ntools: WebFetch\n---\nprompt"
    with pytest.raises(AgentFileError, match="not one this agent can use"):
        parse_agent(text)  # the default list is the planner server's tools
    assert parse_agent(text, available_tools=["WebFetch"]).tools == ("WebFetch",)


def test_command_allows_only_webfetch_on_mines_domains() -> None:
    command = checker.checker_command()
    assert command[command.index("--tools") + 1] == "WebFetch"
    allowed = command[command.index("--allowedTools") + 1:command.index("--strict-mcp-config")]
    assert allowed and all(a.startswith("WebFetch(domain:") and a.endswith("mines.edu)") for a in allowed)
    assert command[command.index("--setting-sources") + 1] == ""
    assert json.loads(command[command.index("--json-schema") + 1]) == checker.VERDICT_SCHEMA
    assert "--no-session-persistence" in command


def test_first_message_has_the_plan_but_not_our_data_or_flags(connection, ex2) -> None:
    message = checker.first_message(connection, ex2, plan_response(ex2))
    assert "Electrical Engineering, M.S. (Non-Thesis)" in message
    assert "EENG509, 3 credits, transfer credit from Front Range State University" in message
    assert "Fall 2026 (3 credits):" in message and "EENG525 Antennas, 3 credits" in message
    assert "no summers" in message
    for leak in ("requirement_groups", "flags", "requirements_met", "also_must", "EE Core"):
        assert leak not in message


def test_run_checker_passes_command_message_and_a_temp_dir(connection, ex2) -> None:
    seen = {}

    def runner(command, message, cwd):
        seen.update(command=command, message=message, cwd=cwd)
        return answer("does_not_work", [BLOCKING])

    verdict = checker.run_checker(connection, ex2, plan_response(ex2), runner=runner)
    assert verdict.status == "does_not_work"
    assert seen["command"] == checker.checker_command()
    assert "Review this degree plan." in seen["message"]
    assert "degree-planner-checker-" in str(seen["cwd"])
    assert verdict.usage == Usage(input_tokens=150, output_tokens=20, steps=7)


def test_no_plan_is_an_error_without_running(connection, ex2) -> None:
    response = AgentResponse(status="cannot_work", plan=None, explanation="x", problems=("p",),
                             usage=Usage(input_tokens=0, output_tokens=0, steps=0))
    verdict = checker.run_checker(connection, ex2, response, runner=lambda *a: pytest.fail("ran"))
    assert verdict.status == "error"


# ------------------------------------------------------------------------------ the verdict

def test_works_with_concerns_only() -> None:
    verdict = checker.parse_run(answer("works", [CONCERN]))
    assert verdict.status == "works" and verdict.blocking == () and len(verdict.findings) == 1


def test_does_not_work_with_a_cited_blocking_finding() -> None:
    verdict = checker.parse_run(answer("does_not_work", [BLOCKING, CONCERN]))
    assert verdict.status == "does_not_work" and verdict.blocking[0].url == GOOD_PAGE


def test_the_final_message_is_read_when_there_is_no_structured_output() -> None:
    assert checker.parse_run(answer("does_not_work", [BLOCKING], where="result")).status == "does_not_work"


@pytest.mark.parametrize("run, reason", [
    (answer("does_not_work", [BLOCKING | {"url": "https://example.com/catalog"}]), "without a Mines URL"),
    (answer("does_not_work", [BLOCKING | {"url": "https://mines.edu.evil.com/x"}]), "without a Mines URL"),
    (answer("does_not_work", [BLOCKING | {"quote": "  "}]), "without a Mines URL and quote"),
    (answer("does_not_work", [CONCERN]), "no blocking finding"),
    (answer("works", [BLOCKING]), "lists blocking findings"),
    (answer("works", [], pages=[]), "no Mines page was read"),
    (answer("works", [], pages=["https://example.com"]), "no Mines page was read"),
    (ClaudeRun(result={"subtype": "success", "result": "I think it works."}), "not JSON"),
    (ClaudeRun(result={"subtype": "success", "structured_output": {"verdict": "maybe"}}), "wrong shape"),
    (ClaudeRun(result={"subtype": "error_max_turns"}), "turns"),
    (ClaudeRun(result={"subtype": "error_during_execution", "is_error": True}), "stopped with"),
    (ClaudeRun(result=None, timed_out=True), "longer than"),
])
def test_inconsistent_or_failed_answers_are_errors_not_verdicts(run: ClaudeRun, reason: str) -> None:
    verdict = checker.parse_run(run)
    assert verdict.status == "error"
    assert reason in (verdict.error or "")


@pytest.mark.parametrize("url, ok", [
    ("https://catalog.mines.edu/coursesaz/compsci/", True),
    ("https://mines.edu/registrar/", True),
    ("http://registrar.mines.edu/core-curriculum/", True),
    ("https://notmines.edu/", False),
    ("https://mines.edu.example.com/", False),
    ("ftp://catalog.mines.edu/", False),
    ("catalog.mines.edu/coursesaz/", False),
])
def test_is_mines_url(url: str, ok: bool) -> None:
    assert checker.is_mines_url(url) is ok
