"""Agent loop: plan, check, revise (plans/AGENT-PLAN.md, task "Agent loop").

Claude Code is the loop: run_agent starts `claude -p` (headless Claude Code) on the machine's
Claude Code login, with every built-in tool turned off and the planner's five tools served by
mcp_server.py. Claude Code calls the tools until it is done or reaches the step limit; then
run_agent rebuilds and validates the last plan check_plan accepted and returns an AgentResponse:
status "ok" with a validated plan, or "cannot_work" with the problems.
The format both ways is docs/agent-request-format.md.

The machine running the backend must have Claude Code installed and signed in (`claude` on PATH).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from degree_planner_backend import validator
from degree_planner_backend.agent import tools
from degree_planner_backend.agent.mcp_server import SERVER_NAME, TOOL_DEFINITIONS, context_for
from degree_planner_backend.agent.request_models import (
    EXPLANATION_MAX,
    PROBLEM_MAX,
    PROBLEMS_MAX,
    AgentRequest,
    AgentResponse,
    Usage,
    _has_visible_text,
)
from degree_planner_backend.plan_models import Plan

logger = logging.getLogger(__name__)

CLAUDE_COMMAND = "claude"
MODEL = "claude-sonnet-5-5"
# Recommended starting point for multistep tool use on Sonnet 5.5; tune with the eval like STEP_LIMIT.
EFFORT = "medium"
# Longest one request may run before it is stopped, in seconds.
TIMEOUT_SECONDS = 600

# Most model turns one request may take (Claude Code's --max-turns, reported as Usage.steps)
# before the loop returns "cannot_work". Placeholder set generously so it does not decide the
# outcome yet; to be tuned from the usage.steps of real runs (Example 1 first, then the eval
# runner) and recorded in DECISIONS.md.
STEP_LIMIT = 25

# Replaces Claude Code's own system prompt, and is the same for every request; the student's
# details and the semester labels go in the first message instead. The loop, not the model,
# decides "ok" or "cannot_work" from the last check_plan result; the model's final message
# becomes the explanation.
SYSTEM_PROMPT = """\
You are the degree planner for Colorado School of Mines students. You build a semester-by-semester \
course plan that meets every requirement of the student's programs (bachelor's, master's, combined \
BS+MS, minors, ASIs) in the semesters they asked for.

Only use what the tools return
- Plan only with courses that search_catalog, get_prerequisites or get_program_requirements returned. \
Never invent a course code, title, credit count, prerequisite or requirement, and never fill a gap \
from what you remember about Mines or any other school.
- If the data is missing something you need (a course, a program, a prerequisite), say so plainly \
instead of guessing.

How to work
1. Call get_program_requirements for each of the student's programs.
2. Look up prerequisites for the courses you plan to use; ask for several courses in one turn \
where you can.
3. Place courses only into the semester labels you were given, in that order, with no others. \
Leave out courses the student has already completed.
4. Call check_plan with the whole plan. Fix every error it reports and call check_plan again. \
Repeat until requirements_met is true.
5. If a requirement cannot be met in the semesters given, stop and say which requirement and why, \
rather than handing back a plan that only looks finished.

The student stays in charge
- The student cannot answer you during this run; they will see your plan and your message on the \
planner page and can change the plan there.
- Never decide an exception for the student. If a course needs an exception (open_exceptions in \
check_plan), keep the course only when the plan needs it, and name it in your message so the \
student can decide.
- When you make a choice the requirements leave open, such as which elective fills a group, \
say which choice you made so the student can change it.

Your final message
When you are done, reply without calling a tool. Write to the student in plain sentences: what the \
plan does, the choices you made, any exceptions they need to decide, and, if the plan does not \
work, what is blocking it. Keep it under 4,000 characters.
"""

# Claude Code names an MCP tool mcp__<server>__<tool>; only these may run, without asking.
ALLOWED_TOOLS = [f"mcp__{SERVER_NAME}__{tool['name']}" for tool in TOOL_DEFINITIONS]

NO_PLAN_PROBLEM = "The agent never sent a plan that check_plan could read."
NOT_MET_PROBLEM = "The plan does not meet every requirement of the student's programs yet."
STEP_LIMIT_PROBLEM = f"The agent stopped after {STEP_LIMIT} steps without finishing."
TIMEOUT_PROBLEM = f"The agent took longer than {TIMEOUT_SECONDS} seconds and was stopped."
STOPPED_PROBLEM = "The agent stopped with an error before it finished."
EMPTY_EXPLANATION = "The agent finished without writing an explanation."


class ClaudeCodeError(RuntimeError):
    """Claude Code could not run at all (not installed, not signed in, unreadable output).
    A server problem, not something about the student's plan, so it is raised, not "cannot_work"."""


@dataclass(frozen=True)
class ClaudeRun:
    """What one `claude -p` run returned: its JSON result, or timed_out."""

    result: dict[str, Any] | None
    timed_out: bool = False


# (command, first message, working directory) -> ClaudeRun. Replaced in tests.
Runner = Callable[[list[str], str, Path], ClaudeRun]


def run_agent(connection: sqlite3.Connection, request: AgentRequest, runner: Runner | None = None) -> AgentResponse:
    """Plan for the student in request and return the checked result."""
    runner = runner or run_claude
    with tempfile.TemporaryDirectory(prefix="degree-planner-agent-") as tmp:
        work = Path(tmp)
        request_path = work / "request.json"
        request_path.write_text(request.model_dump_json(by_alias=True))
        plan_path = work / "plan.json"
        config_path = work / "mcp.json"
        config_path.write_text(json.dumps(_mcp_config(_database_file(connection, work), request_path, plan_path)))

        run = runner(claude_command(config_path), _first_message(request), work)
        plan_input = json.loads(plan_path.read_text()) if plan_path.exists() else None

    stop_problem: str | None = None
    if run.timed_out:
        stop_problem = TIMEOUT_PROBLEM
        final_text, usage = "", Usage(input_tokens=0, output_tokens=0, steps=0)
    else:
        result = run.result or {}
        usage = _usage(result)
        final_text = result.get("result", "") if isinstance(result.get("result"), str) else ""
        if result.get("subtype") == "error_max_turns":
            stop_problem = STEP_LIMIT_PROBLEM
        elif result.get("is_error") or result.get("subtype") != "success":
            logger.warning("claude -p stopped with %r", result.get("subtype"))
            stop_problem = STOPPED_PROBLEM
            final_text = ""  # on an error the result text is Claude Code's message, not the agent's
    return _build_response(connection, context_for(request), plan_input, final_text.strip(), stop_problem, usage)


def claude_command(config_path: Path) -> list[str]:
    return [
        CLAUDE_COMMAND,
        "-p",
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",  # no built-in tools: no files, shell or web, only the planner's
        "--strict-mcp-config", "--mcp-config", str(config_path),
        "--allowedTools", *ALLOWED_TOOLS,
        "--setting-sources", "",  # ignore the machine's Claude Code settings, hooks and plugins
        "--model", MODEL,
        "--effort", EFFORT,
        "--max-turns", str(STEP_LIMIT),
        "--output-format", "json",
        "--no-session-persistence",
    ]


def run_claude(command: list[str], first_message: str, cwd: Path) -> ClaudeRun:
    """Run `claude -p` with the first message on stdin. Runs in the temporary directory, so no
    project's CLAUDE.md is picked up."""
    try:
        completed = subprocess.run(
            command, input=first_message, capture_output=True, text=True, cwd=cwd, timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ClaudeCodeError(f"{CLAUDE_COMMAND!r} is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired:
        return ClaudeRun(result=None, timed_out=True)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        # For example, Claude Code is not signed in. stderr goes to the log, never to the student.
        logger.error("claude -p exited %s: %s", completed.returncode, completed.stderr.strip()[:2000])
        raise ClaudeCodeError(f"claude -p exited {completed.returncode} without a JSON result") from exc
    if not isinstance(result, dict):
        raise ClaudeCodeError("claude -p returned JSON that is not an object")
    return ClaudeRun(result=result)


def _mcp_config(db_path: Path, request_path: Path, plan_path: Path) -> dict[str, Any]:
    return {
        "mcpServers": {
            SERVER_NAME: {
                "type": "stdio",
                # The backend's own Python, so the server runs with the same installed packages.
                "command": sys.executable,
                "args": [
                    "-m", "degree_planner_backend.agent.mcp_server",
                    "--db", str(db_path), "--request", str(request_path), "--plan", str(plan_path),
                ],
            }
        }
    }


def _database_file(connection: sqlite3.Connection, work: Path) -> Path:
    """The file behind connection, which the MCP server opens itself. An in-memory database
    (tests) is copied to a file in the work directory first."""
    for _, name, filename in connection.execute("PRAGMA database_list"):
        if name == "main" and filename:
            return Path(filename)
    copy_path = work / "catalog.db"
    copy = sqlite3.connect(copy_path)
    try:
        connection.backup(copy)
    finally:
        copy.close()
    return copy_path


def _first_message(request: AgentRequest) -> str:
    labels = request.semester_labels()
    student = request.student.model_dump(mode="json", by_alias=True)
    overrides = [{"type": o.type, "code": o.code} for o in request.overrides]
    return (
        "Plan for this student.\n\n"
        f"Student record:\n{json.dumps(student, indent=2)}\n\n"
        f"Semester labels, in order ({len(labels)}): {json.dumps(labels)}\n"
        "Send check_plan every one of these labels in this order, with an empty course list for a "
        "semester that needs no courses.\n\n"
        f"Exceptions the student already overrode: {json.dumps(overrides) if overrides else 'none'}"
    )


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _usage(result: dict[str, Any]) -> Usage:
    """Totals for the whole run from Claude Code's result. All input counts, cached or not, so
    the eval's token numbers are the whole request."""
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    input_tokens = sum(_count(usage.get(key)) for key in
                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    output_tokens = _count(usage.get("output_tokens"))
    steps = _count(result.get("num_turns"))
    if steps == 0 and (input_tokens or output_tokens):
        steps = 1
    return Usage(input_tokens=input_tokens, output_tokens=output_tokens, steps=steps)


def _build_response(
    connection: sqlite3.Connection,
    context: tools.StudentContext,
    plan_input: dict[str, Any] | None,
    final_text: str,
    stop_problem: str | None,
    usage: Usage,
) -> AgentResponse:
    """Rebuild and validate the last plan check_plan accepted, and decide the status from that."""
    explanation = final_text[:EXPLANATION_MAX] if _has_visible_text(final_text) else EMPTY_EXPLANATION
    problems: list[str] = []
    plan: Plan | None = None

    if plan_input is not None:
        built = tools.build_plan(connection, context, tools._parse_semesters(plan_input))
        checked = validator.check_plan(connection, built.validation_plan)
        # The student's record as given, not the cleaned-up copy used for checking (BuiltPlan).
        plan = Plan(
            student=built.plan.student,
            semesters=checked.semesters,
            prerequisite_edges=checked.prerequisite_edges,
            flags=checked.flags,
            summary=checked.summary,
        )
        problems += [issue["message"] for issue in built.errors]
        problems += [
            flag.message for flag in checked.flags
            if flag.severity == "error" and not (flag.overridden and flag.type in tools.OVERRIDABLE_FLAG_TYPES)
        ]
        summary = checked.summary
        if not summary.requirements_met or summary.total_credits < summary.total_credits_required:
            problems.append(NOT_MET_PROBLEM)
    else:
        problems.append(NO_PLAN_PROBLEM)

    if stop_problem is not None:
        problems.insert(0, stop_problem)

    # Same limits as AgentResponse; problems are deduped, keeping the first of each.
    problems = list(dict.fromkeys(p[:PROBLEM_MAX] for p in problems if _has_visible_text(p)))[:PROBLEMS_MAX]
    status = "cannot_work" if problems else "ok"
    return AgentResponse(status=status, plan=plan, explanation=explanation, problems=tuple(problems), usage=usage)
