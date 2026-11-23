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


ALL_VERIFIED = {"program_requirements": True, "prerequisites": True, "credits": True}


def answer(verdict: str, findings: list[dict], pages: list[str] | None = None, *, where: str = "structured_output",
           verified: dict | None = None, **result: object) -> ClaudeRun:
    body = {"verdict": verdict, "summary": "s", "findings": findings, "pages_read": [GOOD_PAGE] if pages is None else pages,
            "verified": ALL_VERIFIED if verified is None else verified}
    out = {"subtype": "success", "is_error": False, "num_turns": 7,
           "usage": {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 20}} | result
    if where == "structured_output":
        out["structured_output"] = body
    else:
        out["result"] = json.dumps(body)
    return ClaudeRun(result=out)


# ------------------------------------------------------------------------------- the command

def test_checker_md_loads_with_webfetch_and_the_pdf_tools() -> None:
    assert checker.AGENT.tools == ("WebFetch", "list_pdfs", "search_pdfs", "read_pdf_pages", "lookup_courses")
    assert checker.AGENT.name == "checker"


def test_agent_file_still_rejects_tools_the_agent_cannot_use() -> None:
    text = "---\nname: x\nmodel: m\neffort: low\nmaxTurns: 3\ntools: WebFetch\n---\nprompt"
    with pytest.raises(AgentFileError, match="not one this agent can use"):
        parse_agent(text)  # the default list is the planner server's tools
    assert parse_agent(text, available_tools=["WebFetch"]).tools == ("WebFetch",)


def test_command_allows_webfetch_on_mines_domains_and_the_pdf_tools(tmp_path: Path) -> None:
    command = checker.checker_command(tmp_path / "mcp.json")
    assert command[command.index("--tools") + 1] == "WebFetch"
    allowed = command[command.index("--allowedTools") + 1:command.index("--strict-mcp-config")]
    web = [a for a in allowed if a.startswith("WebFetch")]
    assert web and all(a.startswith("WebFetch(domain:") and a.endswith("mines.edu)") for a in web)
    assert [a for a in allowed if not a.startswith("WebFetch")] == [
        "mcp__catalog__list_pdfs", "mcp__catalog__search_pdfs", "mcp__catalog__read_pdf_pages",
        "mcp__catalog__lookup_courses"]
    assert command[command.index("--mcp-config") + 1] == str(tmp_path / "mcp.json")
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
    config = seen["cwd"] / "mcp.json"
    assert seen["command"] == checker.checker_command(config)
    server = checker.mcp_config()["mcpServers"]["catalog"]
    assert server["args"][:2] == ["-m", "degree_planner_backend.agent.catalog_pdf_server"]
    assert Path(server["args"][-1]) == REPO_ROOT / "data"
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
    (answer("does_not_work", [BLOCKING | {"url": "https://example.com/catalog"}]), "without a Mines URL, or a catalog"),
    (answer("does_not_work", [BLOCKING | {"url": "https://mines.edu.evil.com/x"}]), "without a Mines URL, or a catalog"),
    (answer("does_not_work", [BLOCKING | {"quote": "  "}]), "without a Mines URL, or a catalog"),
    (answer("does_not_work", [CONCERN]), "no blocking finding"),
    (answer("works", [BLOCKING]), "lists blocking findings"),
    (answer("works", [], pages=[]), "no Mines page or catalog source was read"),
    (answer("works", [], pages=["https://example.com"]), "no Mines page or catalog source was read"),
    (answer("works", [CONCERN], verified={"program_requirements": False, "prerequisites": False, "credits": True}),
     "could not verify program requirements, prerequisites"),
    (answer("works", [], verified={"program_requirements": True, "prerequisites": True, "credits": False}),
     "could not verify credits"),
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


# --------------------------------------------------------------------------- PDF citations

CS_PDF = "pdf:Undergraduate Programs/Computer Science/Computer Science.pdf#page=2"


def test_a_pdf_citation_with_a_quote_on_that_page_counts() -> None:
    finding = BLOCKING | {"url": CS_PDF, "quote": "CSCI370 ADVANCED SOFTWARE ENGINEERING"}
    assert checker.parse_run(answer("does_not_work", [finding])).status == "does_not_work"


def test_a_works_verdict_from_pdfs_alone_counts() -> None:
    assert checker.parse_run(answer("works", [CONCERN], pages=[CS_PDF])).status == "works"


@pytest.mark.parametrize("url, quote", [
    (CS_PDF, "CSCI370 is offered only in the spring"),  # not on that page: made up
    ("pdf:Undergraduate Programs/Computer Science/Computer Science.pdf#page=99", "CSCI370"),  # no such page
    ("pdf:json/courses.json#page=1", "CSCI370"),  # not a catalog PDF
    ("pdf:../secrets.pdf#page=1", "x"),
    ("Undergraduate Programs/Computer Science/Computer Science.pdf, page 2", "CSCI370"),  # not the citation form
])
def test_a_pdf_citation_that_does_not_hold_up_is_an_error(url: str, quote: str) -> None:
    verdict = checker.parse_run(answer("does_not_work", [BLOCKING | {"url": url, "quote": quote}]))
    assert verdict.status == "error"
    assert "course entry that contains the quote" in (verdict.error or "")


def test_a_course_entry_citation_with_a_quote_from_that_row_counts() -> None:
    finding = BLOCKING | {"url": "csv:mines-courses.csv#CSCI210", "quote": "SYSTEMS PROGRAMMING"}
    assert checker.parse_run(answer("does_not_work", [finding])).status == "does_not_work"


@pytest.mark.parametrize("url, quote", [
    ("csv:mines-courses.csv#CSCI210", "offered only in the summer"),  # not in that row
    ("csv:mines-courses.csv#CSCI999", "x"),  # no such course
    ("csv:courses.json#CSCI210", "SYSTEMS"),  # not a course list
])
def test_a_course_citation_that_does_not_hold_up_is_an_error(url: str, quote: str) -> None:
    assert checker.parse_run(answer("does_not_work", [BLOCKING | {"url": url, "quote": quote}])).status == "error"


# ------------------------------------------------------------------------------- terms offered

TERM = {"severity": "blocking", "topic": "term_offered", "claim": "MNGN308 is summer only but planned in Fall 2027",
        "url": GOOD_PAGE, "quote": "12 credits of core courses"}


def test_the_schema_asks_for_a_topic_on_every_finding() -> None:
    item = checker.VERDICT_SCHEMA["properties"]["findings"]["items"]
    assert "topic" in item["required"] and "term_offered" in item["properties"]["topic"]["enum"]


def test_a_term_offered_finding_alone_is_flagged_and_the_plan_works() -> None:
    verdict = checker.parse_run(answer("does_not_work", [TERM, CONCERN]))
    assert verdict.status == "works" and verdict.blocking == ()
    flagged = verdict.findings[0]
    assert flagged.severity == "concern" and flagged.claim.startswith(checker.TERM_FLAG)


def test_a_term_offered_finding_without_a_source_is_still_only_a_concern() -> None:
    # Concerns need no citation, so an uncited term finding does not make the answer an error.
    verdict = checker.parse_run(answer("does_not_work", [TERM | {"url": "", "quote": ""}]))
    assert verdict.status == "works"


def test_another_blocking_finding_still_fails_the_plan() -> None:
    verdict = checker.parse_run(answer("does_not_work", [TERM, BLOCKING]))
    assert verdict.status == "does_not_work"
    assert [f.claim for f in verdict.blocking] == [BLOCKING["claim"]]
    assert verdict.findings[0].severity == "concern"


def test_a_flagged_plan_still_needs_everything_verified() -> None:
    verdict = checker.parse_run(answer("does_not_work", [TERM],
                                       verified={"program_requirements": True, "prerequisites": True, "credits": False}))
    assert verdict.status == "error" and "could not verify credits" in (verdict.error or "")


def test_the_prompt_says_terms_offered_never_fail_the_plan() -> None:
    assert "term_offered" in checker.AGENT.system_prompt and "never fail the plan" in checker.AGENT.system_prompt
