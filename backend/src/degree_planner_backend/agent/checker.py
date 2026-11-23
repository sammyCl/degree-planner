"""The adversarial checker for the local example eval (plans/AGENT-PLAN.md, "Eval runner").

run_checker(connection, example, response) gives the planner's final plan to a second headless
Claude Code run (checker.md) whose only tool is WebFetch, allowed only on Mines domains. It tries to
show the plan would not work, from the live Mines websites, and must answer with the JSON in
VERDICT_SCHEMA. It deliberately gets neither our data/json nor the validator's flags, so its check is
independent of them.

The verdict is read strictly. "works" or "does_not_work" only when the answer is consistent:
every blocking finding cites a Mines URL and quotes it, does_not_work has at least one blocking
finding, works has none and lists the pages read. Anything else is "error": not a pass, but
reported apart from a real failure, so a broken checker is not mistaken for a broken plan.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.agent_file import load_agent
from degree_planner_backend.agent.eval_checks import Example
from degree_planner_backend.agent.request_models import AgentResponse, Usage
from degree_planner_backend.lookups import NotFoundError, get_program

logger = logging.getLogger(__name__)

AGENT = load_agent(Path(__file__).with_name("checker.md"), available_tools=["WebFetch"])
# WebFetch is allowed only on these hosts; in -p mode any other fetch is refused, not asked about.
ALLOWED_DOMAINS = ("catalog.mines.edu", "www.mines.edu", "mines.edu", "registrar.mines.edu", "cs.mines.edu")
TIMEOUT_SECONDS = 1200

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "summary", "findings", "pages_read"],
    "properties": {
        "verdict": {"type": "string", "enum": ["works", "does_not_work"]},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "claim", "url", "quote"],
                "properties": {
                    "severity": {"type": "string", "enum": ["blocking", "concern"]},
                    "claim": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
        "pages_read": {"type": "array", "items": {"type": "string"}},
    },
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    severity: Literal["blocking", "concern"]
    claim: str
    url: str
    quote: str


class _RawVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    verdict: Literal["works", "does_not_work"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    pages_read: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class CheckerVerdict:
    status: Literal["works", "does_not_work", "error"]
    summary: str = ""
    findings: tuple[Finding, ...] = ()
    pages_read: tuple[str, ...] = ()
    error: str | None = None
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=0, output_tokens=0, steps=0))

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocking")


def is_mines_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and (host == "mines.edu" or host.endswith(".mines.edu"))


def checker_command() -> list[str]:
    return [
        loop.CLAUDE_COMMAND,
        "-p",
        "--system-prompt", AGENT.system_prompt,
        "--tools", ",".join(AGENT.tools),  # WebFetch only: no files, shell or search
        "--allowedTools", *[f"WebFetch(domain:{domain})" for domain in ALLOWED_DOMAINS],
        "--strict-mcp-config",  # and no MCP servers
        "--setting-sources", "",  # ignore the machine's Claude Code settings, hooks and plugins
        "--model", AGENT.model,
        "--effort", AGENT.effort,
        "--max-turns", str(AGENT.max_turns),
        "--output-format", "json",
        "--json-schema", json.dumps(VERDICT_SCHEMA),
        "--no-session-persistence",
    ]


def first_message(connection: sqlite3.Connection, example: Example, response: AgentResponse) -> str:
    """The student and the plan, and nothing from our data beyond the programs' names."""
    request = example.request
    student = request.student
    assert response.plan is not None
    programs = []
    for program_id in student.programs:
        try:
            program = get_program(connection, program_id, student.catalog_year)
        except NotFoundError:
            programs.append(program_id)
            continue
        parts = ""
        if program.combines:
            names = []
            for component in program.combines:
                try:
                    names.append(get_program(connection, component, student.catalog_year).name)
                except NotFoundError:
                    names.append(component)
            parts = f" (combines: {'; '.join(names)})"
        programs.append(f"{program.name}{parts}")
    completed = [
        f"- {c.code}, {c.credits:g} credits, "
        + (f"transfer credit from {c.transfer_from}" if c.term == "transfer" and c.transfer_from
           else "transfer credit" if c.term == "transfer" else f"taken at Mines in {c.term}")
        for c in student.completed_courses
    ]
    semesters = []
    for semester in response.plan.semesters:
        planned = [c for c in semester.courses if c.status == "planned"]
        credits = sum(c.credits for c in planned)
        lines = [f"  - {c.code} {c.title}, {c.credits:g} credits" for c in planned] or ["  - (no courses)"]
        semesters.append(f"{semester.label} ({credits:g} credits):\n" + "\n".join(lines))
    return (
        "Review this degree plan.\n\n"
        f"Catalog year: {student.catalog_year}\n"
        f"Programs: {'; '.join(programs)}\n"
        f"The student wants to finish in these {len(response.plan.semesters)} semesters, "
        f"{'summers included' if request.include_summers else 'no summers'}.\n\n"
        "Already completed:\n" + ("\n".join(completed) if completed else "- nothing") + "\n\n"
        "The plan:\n" + "\n\n".join(semesters)
    )


def run_checker(connection: sqlite3.Connection, example: Example, response: AgentResponse,
                runner: loop.Runner | None = None) -> CheckerVerdict:
    if response.plan is None:
        return CheckerVerdict(status="error", error="the agent returned no plan to check")
    runner = runner or (lambda command, message, cwd: loop.run_claude(command, message, cwd, timeout=TIMEOUT_SECONDS))
    with tempfile.TemporaryDirectory(prefix="degree-planner-checker-") as tmp:
        run = runner(checker_command(), first_message(connection, example, response), Path(tmp))
    return parse_run(run)


def parse_run(run: loop.ClaudeRun) -> CheckerVerdict:
    if run.timed_out:
        return CheckerVerdict(status="error", error=f"the checker took longer than {TIMEOUT_SECONDS} seconds")
    result = run.result or {}
    usage = loop._usage(result)
    if result.get("subtype") == "error_max_turns":
        return CheckerVerdict(status="error", error=f"the checker stopped after {AGENT.max_turns} turns", usage=usage)
    if result.get("is_error") or result.get("subtype") != "success":
        return CheckerVerdict(status="error", error=f"the checker stopped with {result.get('subtype')!r}", usage=usage)

    raw = result.get("structured_output")
    if raw is None:  # no structured output: fall back to the final message as JSON
        try:
            raw = json.loads(result.get("result") or "")
        except (TypeError, json.JSONDecodeError):
            return CheckerVerdict(status="error", error="the checker's answer is not JSON", usage=usage)
    try:
        verdict = _RawVerdict.model_validate(raw)
    except ValidationError as exc:
        return CheckerVerdict(status="error", error=f"the checker's answer has the wrong shape: {exc.errors()[0]['msg']}",
                              usage=usage)
    return _judge(verdict, usage)


def _judge(verdict: _RawVerdict, usage: Usage) -> CheckerVerdict:
    blocking = [f for f in verdict.findings if f.severity == "blocking"]
    uncited = [f for f in blocking if not is_mines_url(f.url) or not f.quote.strip()]
    problem = None
    if uncited:
        problem = f"{len(uncited)} blocking finding(s) without a Mines URL and quote"
    elif verdict.verdict == "does_not_work" and not blocking:
        problem = "verdict does_not_work but no blocking finding"
    elif verdict.verdict == "works" and blocking:
        problem = "verdict works but it lists blocking findings"
    elif verdict.verdict == "works" and not any(is_mines_url(u) for u in verdict.pages_read):
        problem = "verdict works but no Mines page was read"
    return CheckerVerdict(
        status="error" if problem else verdict.verdict,
        summary=verdict.summary,
        findings=tuple(verdict.findings),
        pages_read=tuple(verdict.pages_read),
        error=problem,
        usage=usage,
    )
