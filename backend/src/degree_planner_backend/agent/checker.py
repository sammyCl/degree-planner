"""The adversarial checker for the local example eval (plans/AGENT-PLAN.md, "Eval runner").

run_checker(connection, example, response) gives the planner's final plan to a second headless
Claude Code run (checker.md). Its tools are WebFetch, allowed only on Mines domains, and the
read-only catalog tools (catalog_pdf_server.py: the PDFs and the catalog's course lists), for when the live catalog site cannot be
reached. It tries to show the plan would not work and must answer with the JSON in VERDICT_SCHEMA.
It deliberately gets neither our data/json nor the validator's flags, so its check is independent
of them.

The verdict is read strictly. "works" or "does_not_work" only when the answer is consistent:
every blocking finding cites a source and quotes it (a Mines URL, or a PDF page or course entry
whose text must contain the quote), does_not_work has at least one blocking finding, and works has none, says it
verified the requirements, prerequisites and credits, and lists the pages read. Anything else is
"error": not a pass, but reported apart from a real failure, so a checker that could not do its
job is never mistaken for a plan that works.

Some findings are flagged, never failed, because our data cannot record them yet, so the planner
cannot be held to them: terms offered ("term_offered", BUG-045) and prerequisites of credits
completed or class standing ("class_standing", BUG-040, e.g. EBGN321's 60 credit hours). A blocking
finding with one of these topics is turned into a concern before the verdict is judged, and if
nothing else blocks, a does_not_work verdict becomes works (still subject to the rules above).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.agent_file import load_agent
from degree_planner_backend.agent.catalog_pdf_server import DATA_DIR, SERVER_NAME, TOOL_NAMES, PdfLibrary
from degree_planner_backend.agent.eval_checks import Example
from degree_planner_backend.agent.request_models import AgentResponse, Usage
from degree_planner_backend.lookups import NotFoundError, get_program

logger = logging.getLogger(__name__)

BUILT_IN_TOOLS = ("WebFetch",)
AGENT = load_agent(Path(__file__).with_name("checker.md"), available_tools=[*BUILT_IN_TOOLS, *TOOL_NAMES])
# WebFetch is allowed only on these hosts; in -p mode any other fetch is refused, not asked about.
ALLOWED_DOMAINS = ("catalog.mines.edu", "www.mines.edu", "mines.edu", "registrar.mines.edu", "cs.mines.edu")
TIMEOUT_SECONDS = 1200
TOPICS = ("requirements", "prerequisites", "class_standing", "credits", "shared_credits", "transfer",
          "term_offered", "other")
# Topics our data cannot check yet: a blocking finding with one becomes a concern, and its claim
# starts with this text.
FLAGGED_TOPICS = {
    "term_offered": "[term offered: flagged, not failed] ",
    "class_standing": "[class standing: flagged, not failed] ",
}

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "summary", "findings", "pages_read", "verified"],
    "properties": {
        "verdict": {"type": "string", "enum": ["works", "does_not_work"]},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "topic", "claim", "url", "quote"],
                "properties": {
                    "severity": {"type": "string", "enum": ["blocking", "concern"]},
                    "topic": {"type": "string", "enum": list(TOPICS)},
                    "claim": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
        "pages_read": {"type": "array", "items": {"type": "string"}},
        "verified": {
            "type": "object",
            "additionalProperties": False,
            "required": ["program_requirements", "prerequisites", "credits"],
            "properties": {
                "program_requirements": {"type": "boolean"},
                "prerequisites": {"type": "boolean"},
                "credits": {"type": "boolean"},
            },
        },
    },
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    severity: Literal["blocking", "concern"]
    # Default "other" so results saved before the field existed still load.
    topic: Literal["requirements", "prerequisites", "class_standing", "credits", "shared_credits", "transfer",
                   "term_offered", "other"] = "other"
    claim: str
    url: str
    quote: str


class Verified(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    program_requirements: bool
    prerequisites: bool
    credits: bool


class _RawVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    verdict: Literal["works", "does_not_work"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    pages_read: list[str] = Field(default_factory=list)
    verified: Verified


@dataclass(frozen=True)
class CheckerVerdict:
    status: Literal["works", "does_not_work", "error"]
    summary: str = ""
    findings: tuple[Finding, ...] = ()
    pages_read: tuple[str, ...] = ()
    verified: Verified | None = None
    error: str | None = None
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=0, output_tokens=0, steps=0))

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocking")


def is_mines_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and (host == "mines.edu" or host.endswith(".mines.edu"))


@lru_cache(maxsize=1)
def default_library() -> PdfLibrary:
    return PdfLibrary(DATA_DIR)


def mcp_config(root: Path = DATA_DIR) -> dict[str, Any]:
    return {"mcpServers": {SERVER_NAME: {
        "type": "stdio",
        "command": sys.executable,  # the backend's own Python, with pypdf and mcp installed
        "args": ["-m", "degree_planner_backend.agent.catalog_pdf_server", "--root", str(root)],
    }}}


def checker_command(config_path: Path) -> list[str]:
    built_in = [t for t in AGENT.tools if t in BUILT_IN_TOOLS]
    pdf_tools = [f"mcp__{SERVER_NAME}__{t}" for t in AGENT.tools if t in TOOL_NAMES]
    return [
        loop.CLAUDE_COMMAND,
        "-p",
        "--system-prompt", AGENT.system_prompt,
        "--tools", ",".join(built_in),  # WebFetch only: no files, shell or search
        "--allowedTools", *[f"WebFetch(domain:{domain})" for domain in ALLOWED_DOMAINS], *pdf_tools,
        "--strict-mcp-config", "--mcp-config", str(config_path),  # only the catalog PDF server
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
        config_path = Path(tmp) / "mcp.json"
        config_path.write_text(json.dumps(mcp_config()))
        run = runner(checker_command(config_path), first_message(connection, example, response), Path(tmp))
    return parse_run(run)


def parse_run(run: loop.ClaudeRun, library: PdfLibrary | None = None) -> CheckerVerdict:
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
    return _judge(verdict, usage, library or default_library())


def is_catalog_citation(source: str, library: PdfLibrary) -> bool:
    return library.page_text(source) is not None


def is_cited(finding: Finding, library: PdfLibrary) -> bool:
    """A Mines URL with a quote, or a real PDF page or course entry whose text contains the quote."""
    if not finding.quote.strip():
        return False
    if is_mines_url(finding.url):
        return True
    return library.quote_on_page(finding.url, finding.quote)


def flag_unchecked_topics(verdict: _RawVerdict) -> _RawVerdict:
    """Turn blocking findings on FLAGGED_TOPICS into concerns; with nothing left blocking, does_not_work becomes works."""
    findings = [f.model_copy(update={"severity": "concern", "claim": FLAGGED_TOPICS[f.topic] + f.claim})
                if f.severity == "blocking" and f.topic in FLAGGED_TOPICS else f
                for f in verdict.findings]
    if findings == list(verdict.findings):
        return verdict
    still_blocked = any(f.severity == "blocking" for f in findings)
    return verdict.model_copy(update={"findings": findings,
                                      "verdict": verdict.verdict if still_blocked else "works"})


def _judge(verdict: _RawVerdict, usage: Usage, library: PdfLibrary) -> CheckerVerdict:
    verdict = flag_unchecked_topics(verdict)
    blocking = [f for f in verdict.findings if f.severity == "blocking"]
    uncited = [f for f in blocking if not is_cited(f, library)]
    unverified = [name for name, ok in verdict.verified.model_dump().items() if not ok]
    problem = None
    if uncited:
        problem = (f"{len(uncited)} blocking finding(s) without a Mines URL, or a catalog PDF page or course entry that contains the quote: "
                   + "; ".join(f.claim[:80] for f in uncited))
    elif verdict.verdict == "does_not_work" and not blocking:
        problem = "verdict does_not_work but no blocking finding"
    elif verdict.verdict == "works" and blocking:
        problem = "verdict works but it lists blocking findings"
    elif verdict.verdict == "works" and unverified:
        problem = "could not verify " + ", ".join(n.replace("_", " ") for n in unverified)
    elif verdict.verdict == "works" and not any(is_mines_url(u) or is_catalog_citation(u, library) for u in verdict.pages_read):
        problem = "verdict works but no Mines page or catalog source was read"
    return CheckerVerdict(
        status="error" if problem else verdict.verdict,
        summary=verdict.summary,
        findings=tuple(verdict.findings),
        pages_read=tuple(verdict.pages_read),
        verified=verdict.verified,
        error=problem,
        usage=usage,
    )
