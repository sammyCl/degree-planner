"""Tests for the agent loop (agent/loop.py). Claude Code is replaced by a fake runner that makes
scripted tool calls through the real PlannerTools from mcp_server.py: no model, no login, no cost."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.loop import (
    ALLOWED_TOOLS,
    EMPTY_EXPLANATION,
    MODEL,
    NO_PLAN_PROBLEM,
    NOT_MET_PROBLEM,
    STEP_LIMIT,
    STEP_LIMIT_PROBLEM,
    STOPPED_PROBLEM,
    SYSTEM_PROMPT,
    TIMEOUT_PROBLEM,
    ClaudeCodeError,
    ClaudeRun,
    claude_command,
    run_agent,
    run_claude,
)
from degree_planner_backend.agent.mcp_server import PlannerTools
from degree_planner_backend.agent.request_models import EXPLANATION_MAX, AgentRequest
from degree_planner_backend.data_loader import refresh_database

# A made-up program small enough to plan by hand: TEST101 then TEST102, 6 credits in all.
PROGRAM = {
    "program_id": "tiny-bs",
    "name": "Tiny Test Major",
    "degree_level": "bachelor",
    "catalog_year": "2026-2027",
    "total_credits_required": 6,
    "requirement_groups": [
        {"group_id": "core", "label": "Core", "kind": "all", "courses": ["TEST101", "TEST102"]},
    ],
}
LABELS = ["Fall 2026", "Spring 2027"]
GOOD_PLAN = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2027", "courses": ["TEST102"]}]}
HALF_PLAN = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2027", "courses": []}]}


def make_course(code: str, **extra: object) -> dict:
    return extra | {
        "code": code,
        "subject": code[:4],
        "number": code[4:],
        "title": f"Test course {code}",
        "credits": 3.0,
        "description": "Made-up course for tests.",
        "catalog_year": "2026-2027",
    }


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    courses = [make_course("TEST101"), make_course("TEST102", prerequisites={"type": "course", "code": "TEST101"})]
    (tmp_path / "data.json").write_text(json.dumps({"courses": courses, "programs": [PROGRAM]}))
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def make_request(**changes: object) -> AgentRequest:
    fields = {
        "student": {"degree_level": "bachelor", "programs": ["tiny-bs"], "catalog_year": "2026-2027"},
        "semesters": 2,
        "start_term": "Fall 2026",
    } | changes
    return AgentRequest.model_validate(fields)


def claude_result(text: str = "Done.", subtype: str = "success", num_turns: int = 2, **usage: int) -> dict:
    return {
        "type": "result",
        "subtype": subtype,
        "is_error": subtype != "success",
        "result": text,
        "num_turns": num_turns,
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                  "output_tokens": 5} | usage,
    }


class FakeClaude:
    """Stands in for `claude -p`: reads the MCP config the loop wrote, starts the planner tools
    from it like Claude Code starts the server, makes the scripted calls, and returns a result."""

    def __init__(self, calls: list[tuple[str, object]] = (), result: dict | None = None, timed_out: bool = False) -> None:
        self.calls = list(calls)
        self.result = claude_result() if result is None and not timed_out else result
        self.timed_out = timed_out
        self.command: list[str] = []
        self.first_message = ""
        self.cwd: Path | None = None
        self.db_path = ""
        self.tool_results: list[dict] = []

    def __call__(self, command: list[str], first_message: str, cwd: Path) -> ClaudeRun:
        self.command, self.first_message, self.cwd = command, first_message, cwd
        config = json.loads(Path(command[command.index("--mcp-config") + 1]).read_text())
        args = config["mcpServers"]["planner"]["args"]
        option = {args[i]: args[i + 1] for i in range(2, len(args), 2)}
        self.db_path = option["--db"]
        request = AgentRequest.model_validate_json(Path(option["--request"]).read_text())
        planner = PlannerTools(sqlite3.connect(option["--db"]), request, Path(option["--plan"]))
        self.tool_results = [planner.call(name, tool_input) for name, tool_input in self.calls]
        return ClaudeRun(result=self.result, timed_out=self.timed_out)


# --- a plan that works --------------------------------------------------------------------------


def test_valid_plan_is_ok(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([("check_plan", GOOD_PLAN)], claude_result("TEST101 first, then TEST102."))
    response = run_agent(connection, make_request(), runner=fake)

    assert response.status == "ok"
    assert response.problems == ()
    assert response.explanation == "TEST101 first, then TEST102."
    assert [s.label for s in response.plan.semesters] == LABELS
    assert [[c.code for c in s.courses] for s in response.plan.semesters] == [["TEST101"], ["TEST102"]]
    assert response.plan.summary.requirements_met


def test_plan_keeps_the_students_record_as_given(connection: sqlite3.Connection) -> None:
    student = {
        "degree_level": "bachelor",
        "programs": ["tiny-bs"],
        "catalog_year": "2026-2027",
        "completed_courses": [{"code": "test 101", "credits": 3.0, "term": "transfer"}],
    }
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST102"]}, {"label": "Spring 2027", "courses": []}]}
    response = run_agent(connection, make_request(student=student), runner=FakeClaude([("check_plan", plan)]))

    assert response.status == "ok"
    # Not the cleaned-up copy check_plan validates with ('TEST101').
    assert response.plan.student.completed_courses[0].code == "test 101"


def test_last_accepted_plan_is_returned(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([("check_plan", GOOD_PLAN), ("check_plan", {"semesters": "not a list"})])
    response = run_agent(connection, make_request(), runner=fake)

    assert "error" in fake.tool_results[1]
    assert response.status == "ok"


def test_file_database_is_used_in_place(tmp_path: Path, connection: sqlite3.Connection) -> None:
    db_file = tmp_path / "catalog.db"
    file_connection = sqlite3.connect(db_file)
    connection.backup(file_connection)
    fake = FakeClaude([("check_plan", GOOD_PLAN)])
    response = run_agent(file_connection, make_request(), runner=fake)

    assert response.status == "ok"
    assert fake.db_path == str(db_file)  # not a copy


def test_in_memory_database_is_copied_for_the_server(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([("check_plan", GOOD_PLAN)])
    run_agent(connection, make_request(), runner=fake)

    assert Path(fake.db_path).parent == fake.cwd


# --- what Claude Code is given ------------------------------------------------------------------


def test_command_turns_off_built_in_tools_and_allows_only_the_planner(tmp_path: Path) -> None:
    command = claude_command(tmp_path / "mcp.json")

    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in command
    assert command[command.index("--setting-sources") + 1] == ""
    start = command.index("--allowedTools") + 1
    assert command[start:start + 5] == ALLOWED_TOOLS == [
        "mcp__planner__search_catalog", "mcp__planner__get_prerequisites",
        "mcp__planner__get_program_requirements", "mcp__planner__get_forms", "mcp__planner__check_plan",
    ]


def test_command_carries_prompt_model_and_limits(tmp_path: Path) -> None:
    command = claude_command(tmp_path / "mcp.json")

    assert command[command.index("--system-prompt") + 1] == SYSTEM_PROMPT
    assert command[command.index("--model") + 1] == MODEL == "claude-sonnet-5-5"
    assert command[command.index("--max-turns") + 1] == str(STEP_LIMIT)
    assert command[command.index("--output-format") + 1] == "json"
    assert "--no-session-persistence" in command


def test_first_message_has_the_request(connection: sqlite3.Connection) -> None:
    fake = FakeClaude()
    run_agent(connection, make_request(overrides=[{"type": "exception_claimed", "code": "test102"}]), runner=fake)

    assert json.dumps(LABELS) in fake.first_message
    assert '"tiny-bs"' in fake.first_message
    assert '"TEST102"' in fake.first_message  # the override, cleaned up


def test_runs_in_a_temporary_directory_that_is_removed(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([("check_plan", GOOD_PLAN)])
    run_agent(connection, make_request(), runner=fake)

    assert fake.cwd is not None
    assert fake.cwd.name.startswith("degree-planner-agent-")
    assert not fake.cwd.exists()


def test_server_gets_the_students_record_from_the_loop(connection: sqlite3.Connection) -> None:
    student = {
        "degree_level": "bachelor",
        "programs": ["tiny-bs"],
        "catalog_year": "2026-2027",
        "completed_courses": [{"code": "TEST101", "credits": 3.0, "term": "transfer"}],
    }
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST102"]}, {"label": "Spring 2027", "courses": []}]}
    fake = FakeClaude([("check_plan", plan)])
    run_agent(connection, make_request(student=student), runner=fake)

    assert fake.tool_results[0]["requirements_met"] is True


# --- plans that do not work ---------------------------------------------------------------------


def test_no_plan_at_all(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), runner=FakeClaude([], claude_result("I could not plan this.")))

    assert response.status == "cannot_work"
    assert response.plan is None
    assert response.problems == (NO_PLAN_PROBLEM,)
    assert response.explanation == "I could not plan this."


def test_rejected_labels_leave_no_plan(connection: sqlite3.Connection) -> None:
    wrong = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101", "TEST102"]}]}
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", wrong)]))

    assert response.status == "cannot_work"
    assert response.plan is None


def test_unfinished_plan_is_cannot_work_with_the_plan(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", HALF_PLAN)]))

    assert response.status == "cannot_work"
    assert response.plan is not None  # the planner page can still draw it
    assert NOT_MET_PROBLEM in response.problems


def test_unknown_course_is_a_problem(connection: sqlite3.Connection) -> None:
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101", "FAKE999"]}, {"label": "Spring 2027", "courses": ["TEST102"]}]}
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", plan)]))

    assert response.status == "cannot_work"
    assert any("FAKE999" in problem for problem in response.problems)


def test_model_saying_done_does_not_make_a_failing_plan_ok(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([("check_plan", HALF_PLAN)], claude_result("All requirements are met!"))
    response = run_agent(connection, make_request(), runner=fake)

    assert response.status == "cannot_work"


# --- stopping -----------------------------------------------------------------------------------


def test_step_limit_keeps_the_last_plan(connection: sqlite3.Connection) -> None:
    # Claude Code's --max-turns result has no final message.
    result = claude_result(subtype="error_max_turns", num_turns=STEP_LIMIT)
    del result["result"]
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", GOOD_PLAN)], result))

    # Even a passing plan is not "ok" when the agent never finished.
    assert response.status == "cannot_work"
    assert response.problems == (STEP_LIMIT_PROBLEM,)
    assert response.plan is not None
    assert response.usage.steps == STEP_LIMIT
    assert response.explanation == EMPTY_EXPLANATION


def test_error_result_is_cannot_work_without_its_text(connection: sqlite3.Connection) -> None:
    result = claude_result("Internal error: something broke", subtype="error_during_execution")
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", GOOD_PLAN)], result))

    assert response.status == "cannot_work"
    assert response.problems[0] == STOPPED_PROBLEM
    assert response.explanation == EMPTY_EXPLANATION  # Claude Code's message is not shown to the student


def test_error_result_is_kept_in_the_failure_log_but_not_the_students_completed_courses(connection: sqlite3.Connection) -> None:
    import json
    import os
    from pathlib import Path

    result = claude_result("API Error: 529 overloaded", subtype="error_during_execution")
    run_agent(connection, make_request(), runner=FakeClaude([("check_plan", GOOD_PLAN)], result))

    lines = (Path(os.environ["DEGREE_PLANNER_LOG_DIR"]) / "agent-failures.jsonl").read_text().splitlines()
    entry = json.loads(lines[-1])
    assert entry["problem"] == STOPPED_PROBLEM
    assert "529 overloaded" in entry["claude_result"]  # the real reason, which the student never sees
    assert "completed_courses" not in entry["request"]
    assert entry["request"]["programs"]


def test_a_run_that_finishes_writes_no_failure_log(connection: sqlite3.Connection) -> None:
    import os
    from pathlib import Path

    run_agent(connection, make_request(), runner=FakeClaude([("check_plan", GOOD_PLAN)], claude_result("Done.")))
    assert not (Path(os.environ["DEGREE_PLANNER_LOG_DIR"]) / "agent-failures.jsonl").exists()


def test_timeout_is_cannot_work_with_the_plan_so_far(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", HALF_PLAN)], timed_out=True))

    assert response.status == "cannot_work"
    assert response.problems[0] == TIMEOUT_PROBLEM
    assert response.plan is not None
    assert response.usage.model_dump() == {"input_tokens": 0, "output_tokens": 0, "steps": 0}


# --- explanation and usage ----------------------------------------------------------------------


def test_explanation_is_trimmed(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), runner=FakeClaude([], claude_result("  Plan below.\n\n")))

    assert response.explanation == "Plan below."


@pytest.mark.parametrize("final", ["", "   ", "​"])
def test_empty_final_message_gets_a_fixed_explanation(connection: sqlite3.Connection, final: str) -> None:
    response = run_agent(connection, make_request(), runner=FakeClaude([], claude_result(final)))

    assert response.explanation == EMPTY_EXPLANATION


def test_long_explanation_is_cut_to_the_limit(connection: sqlite3.Connection) -> None:
    fake = FakeClaude([], claude_result("x" * (EXPLANATION_MAX + 50)))
    response = run_agent(connection, make_request(), runner=fake)

    assert len(response.explanation) == EXPLANATION_MAX


def test_usage_counts_cached_input_too(connection: sqlite3.Connection) -> None:
    result = claude_result(num_turns=4, input_tokens=12, cache_creation_input_tokens=4000,
                           cache_read_input_tokens=9000, output_tokens=300)
    response = run_agent(connection, make_request(), runner=FakeClaude([], result))

    assert response.usage.model_dump() == {"input_tokens": 13012, "output_tokens": 300, "steps": 4}


@pytest.mark.parametrize("usage", [None, "lots", {"input_tokens": -5, "output_tokens": "7"}])
def test_bad_usage_counts_are_treated_as_zero(connection: sqlite3.Connection, usage: object) -> None:
    result = claude_result(num_turns=0) | {"usage": usage}
    response = run_agent(connection, make_request(), runner=FakeClaude([], result))

    assert response.usage.model_dump() == {"input_tokens": 0, "output_tokens": 0, "steps": 0}


def test_tokens_with_no_turn_count_still_count_one_step(connection: sqlite3.Connection) -> None:
    result = claude_result() | {"num_turns": None}
    response = run_agent(connection, make_request(), runner=FakeClaude([], result))

    assert response.usage.steps == 1


# --- run_claude with a stand-in program -------------------------------------------------------


def fake_program(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_claude.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def test_run_claude_sends_the_message_and_reads_json(tmp_path: Path) -> None:
    command = fake_program(tmp_path, "import json, sys\nprint(json.dumps({'subtype': 'success', 'result': sys.stdin.read()}))\n")
    run = run_claude(command, "hello planner", tmp_path)

    assert run.timed_out is False
    assert run.result == {"subtype": "success", "result": "hello planner"}


def test_run_claude_not_installed(tmp_path: Path) -> None:
    with pytest.raises(ClaudeCodeError, match="not installed"):
        run_claude([str(tmp_path / "no-such-claude")], "", tmp_path)


def test_run_claude_output_that_is_not_json(tmp_path: Path) -> None:
    command = fake_program(tmp_path, "import sys\nprint('Invalid API key - please run /login', file=sys.stderr)\nsys.exit(1)\n")
    with pytest.raises(ClaudeCodeError, match="without a JSON result"):
        run_claude(command, "", tmp_path)


def test_run_claude_json_that_is_not_an_object(tmp_path: Path) -> None:
    command = fake_program(tmp_path, "print('[1, 2]')\n")
    with pytest.raises(ClaudeCodeError, match="not an object"):
        run_claude(command, "", tmp_path)


def test_run_claude_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop, "TIMEOUT_SECONDS", 0.5)
    command = fake_program(tmp_path, "import time\ntime.sleep(10)\n")
    run = run_claude(command, "", tmp_path)

    assert run == ClaudeRun(result=None, timed_out=True)


def test_the_returned_plan_keeps_the_validators_labels_and_checklist(connection: sqlite3.Connection) -> None:
    """Regression: run_agent rebuilt the Plan field by field and dropped counts_toward and requirement_status,
    so the planner page showed no course labels and no requirement checklist until the first edit."""
    response = run_agent(connection, make_request(), runner=FakeClaude([("check_plan", HALF_PLAN)]))

    assert response.plan is not None
    assert response.plan.requirement_status, "the requirement checklist was dropped"
    assert response.plan.counts_toward, "the course labels were dropped"
