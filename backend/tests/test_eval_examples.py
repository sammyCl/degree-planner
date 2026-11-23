"""Tests for agent/eval_examples.py, the eval command (agent/eval: Samantha). The agent and the checker
are replaced by fakes, so nothing here calls Claude."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent import eval_examples
from degree_planner_backend.agent.checker import CheckerVerdict, Finding
from degree_planner_backend.agent.loop import ClaudeCodeError
from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse, Usage
from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Summary

EXAMPLE = {
    "id": 1, "name": "one", "difficulty": "simple",
    "request": {"student": {"degree_level": "bachelor", "programs": ["t-major"], "catalog_year": "2026-2027",
                            "completed_courses": []},
                "semesters": 2, "start_term": "Fall 2026", "include_summers": False, "overrides": []},
    "also_must": [{"type": "not_planned", "codes": ["HNRS105"]}],
}


@pytest.fixture
def setup(tmp_path: Path) -> dict[str, Path]:
    examples = tmp_path / "examples"
    (examples / "private").mkdir(parents=True)
    (examples / "ex1.json").write_text(json.dumps(EXAMPLE))
    reviewed = EXAMPLE | {"id": 5, "name": "five", "difficulty": "hard",
                          "also_must": EXAMPLE["also_must"] + [{"type": "review_required", "by": "Sammy"}]}
    (examples / "private" / "ex5.json").write_text(json.dumps(reviewed))
    data = tmp_path / "data"
    data.mkdir()
    (data / "programs.json").write_text(json.dumps({"programs": []}))
    db = tmp_path / "catalog.db"
    conn = sqlite3.connect(db)
    refresh_database(data, conn)
    conn.close()
    return {"examples": examples, "results": tmp_path / "results", "db": db}


def response(request: AgentRequest, codes: list[str], status: str = "ok") -> AgentResponse:
    semesters = [Semester(semester_id=f"s{i}", label=label, courses=[
        PlannedCourse(course_id=f"{label}{c}", code=c, title=c, credits=3.0, status="planned") for c in codes])
        for i, label in enumerate(request.semester_labels())]
    plan = Plan(student=request.student, semesters=semesters,
                summary=Summary(total_credits=6, total_credits_required=6, requirements_met=status == "ok"))
    return AgentResponse(status=status, plan=plan, explanation="x", problems=() if status == "ok" else ("short",),
                         usage=Usage(input_tokens=1000, output_tokens=100, steps=5))


def agent_planning(*codes: str, status: str = "ok"):
    calls = []

    def agent(_conn, request):
        calls.append(request)
        return response(request, list(codes), status)
    agent.calls = calls  # type: ignore[attr-defined]
    return agent


def checker_saying(status: str, findings: tuple[Finding, ...] = (), error: str | None = None):
    calls = []

    def check(_conn, example, resp):
        calls.append(example.id)
        return CheckerVerdict(status=status, summary="s", findings=findings, pages_read=("https://catalog.mines.edu/",),
                              error=error, usage=Usage(input_tokens=500, output_tokens=50, steps=9))
    check.calls = calls  # type: ignore[attr-defined]
    return check


def main(setup, *args: str, agent=None, check=None) -> tuple[int, str]:
    lines: list[str] = []
    code = eval_examples.main(
        [*args, "--db", str(setup["db"]), "--examples-dir", str(setup["examples"]),
         "--results-dir", str(setup["results"])],
        agent=agent or agent_planning("CSCI128"), check=check or checker_saying("works"), out=lines.append)
    return code, "\n".join(lines)


BLOCKING = Finding(severity="blocking", claim="CSCI128 needs MATH111 first", url="https://catalog.mines.edu/x", quote="q")


def run_folder(setup) -> Path:
    (folder,) = setup["results"].iterdir()
    return folder


# -------------------------------------------------------------------------------- outcomes

def test_a_plan_that_passes_everything_passes(setup) -> None:
    code, text = main(setup, "--example", "1")
    assert code == 0
    assert "Example 1 run 1: PASS" in text
    assert "Passed: 1 of 1 runs" in text


def test_a_failed_check_fails_and_says_why(setup) -> None:
    _, text = main(setup, "--example", "1", agent=agent_planning("HNRS105"))
    assert "Example 1 run 1: FAIL" in text
    assert "check not_planned: planned anyway: HNRS105" in text


def test_cannot_work_fails_even_if_the_checker_likes_it(setup) -> None:
    _, text = main(setup, "--example", "1", agent=agent_planning("CSCI128", status="cannot_work"))
    assert "Example 1 run 1: FAIL" in text and "status cannot_work: short" in text


def test_the_checker_can_fail_a_plan_the_checks_pass(setup) -> None:
    _, text = main(setup, "--example", "1", check=checker_saying("does_not_work", (BLOCKING,)))
    assert "Example 1 run 1: FAIL" in text
    assert "checker blocking: CSCI128 needs MATH111 first (https://catalog.mines.edu/x)" in text


def test_a_checker_error_is_reported_apart_from_a_failure(setup) -> None:
    _, text = main(setup, "--example", "1", check=checker_saying("error", error="the checker's answer is not JSON"))
    assert "Example 1 run 1: CHECKER ERROR" in text
    assert "checker error: the checker's answer is not JSON" in text
    assert "Passed: 0 of 1 runs" in text and "1 checker error" in text


def test_no_checker_runs_only_the_checks(setup) -> None:
    check = checker_saying("works")
    _, text = main(setup, "--example", "1", "--no-checker", check=check)
    assert check.calls == []
    assert "DETERMINISTIC ONLY" in text and "checker skipped" in text


def test_runs_repeat_each_example_and_tally(setup) -> None:
    agent = agent_planning("CSCI128")
    _, text = main(setup, "--example", "1", "--runs", "3", agent=agent)
    assert len(agent.calls) == 3
    assert "Example 1: 3 of 3 passed" in text
    assert "Tokens: agent 3000 in / 300 out; checker 1500 in / 150 out" in text


def test_every_run_is_saved_with_its_numbers(setup) -> None:
    main(setup, "--example", "1", "--runs", "2")
    folder = run_folder(setup)
    assert sorted(p.name for p in folder.iterdir()) == ["ex1-run1.json", "ex1-run2.json"]
    record = json.loads((folder / "ex1-run1.json").read_text())
    assert record["outcome"] == "pass"
    assert record["agent"]["usage"] == {"input_tokens": 1000, "output_tokens": 100, "steps": 5}
    assert record["checker"]["usage"]["steps"] == 9
    assert record["response"]["plan"]["semesters"][0]["courses"][0]["code"] == "CSCI128"


# ---------------------------------------------------------------------------------- review

def test_an_example_needing_review_waits_and_tally_applies_the_review(setup) -> None:
    _, text = main(setup, "--example", "5")
    assert "Example 5 run 1: AWAITING REVIEW" in text
    assert "write ex5-run1.review.json" in text
    assert "Passed: 0 of 1 runs" in text

    folder = run_folder(setup)
    (folder / "ex5-run1.review.json").write_text(json.dumps({"verdict": "pass", "notes": "matches my plan"}))
    code, text = main(setup, "--tally", str(folder))
    assert code == 0 and "Example 5 run 1: PASS" in text and "Passed: 1 of 1 runs" in text

    (folder / "ex5-run1.review.json").write_text(json.dumps({"verdict": "fail"}))
    _, text = main(setup, "--tally", str(folder))
    assert "Example 5 run 1: FAIL" in text


def test_a_review_cannot_pass_a_plan_the_checker_failed(setup) -> None:
    main(setup, "--example", "5", check=checker_saying("does_not_work", (BLOCKING,)))
    folder = run_folder(setup)
    (folder / "ex5-run1.review.json").write_text(json.dumps({"verdict": "pass"}))
    _, text = main(setup, "--tally", str(folder))
    assert "Example 5 run 1: FAIL" in text


def test_a_review_with_a_bad_verdict_is_an_error(setup) -> None:
    main(setup, "--example", "5")
    folder = run_folder(setup)
    (folder / "ex5-run1.review.json").write_text(json.dumps({"verdict": "looks fine"}))
    with pytest.raises(ValueError, match="pass"):
        main(setup, "--tally", str(folder))


# ---------------------------------------------------------------------------- checker-only

def test_checker_only_judges_a_saved_response_without_the_agent(setup, tmp_path: Path) -> None:
    request = AgentRequest.model_validate(EXAMPLE["request"])
    saved = tmp_path / "canary.json"
    saved.write_text(response(request, ["CSCI128"]).model_dump_json(by_alias=True))
    agent = agent_planning("CSCI128")
    check = checker_saying("does_not_work", (BLOCKING,))
    _, text = main(setup, "--example", "1", "--checker-only", str(saved), agent=agent, check=check)
    assert agent.calls == [] and check.calls == [1]
    assert "Example 1 run 1: FAIL" in text
    assert (run_folder(setup) / "ex1-run1-checker-only.json").exists()


# --------------------------------------------------------------------------- bad arguments

@pytest.mark.parametrize("args, message", [
    (["--example", "7"], "no example with id 7"),
    (["--runs", "0"], "--runs must be at least 1"),
    (["--checker-only", "x.json"], "needs exactly one --example"),
    (["--tally", "nowhere"], "no results folder"),
])
def test_bad_arguments(setup, args: list[str], message: str) -> None:
    code, text = main(setup, *args)
    assert code == 2 and message in text


def test_missing_database(setup) -> None:
    setup["db"].unlink()
    code, text = main(setup, "--example", "1")
    assert code == 2 and "load-data" in text


def test_claude_code_not_running_stops_the_run(setup) -> None:
    def broken(_conn, _request):
        raise ClaudeCodeError("'claude' is not installed or not on PATH")
    code, text = main(setup, "--example", "1", agent=broken)
    assert code == 1 and "Claude Code could not run" in text
