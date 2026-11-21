"""Tests for the MCP server that gives Claude Code the planner's tools (agent/mcp_server.py).

Most tests call PlannerTools directly; the last ones start the real server as a process and talk
MCP to it, the way Claude Code does. No model is called.
"""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from degree_planner_backend.agent.mcp_server import TOOL_DEFINITIONS, PlannerTools
from degree_planner_backend.agent.request_models import AgentRequest
from degree_planner_backend.data_loader import refresh_database

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
def db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    courses = [make_course("TEST101"), make_course("TEST102", prerequisites={"type": "course", "code": "TEST101"})]
    (data_dir / "data.json").write_text(json.dumps({"courses": courses, "programs": [PROGRAM]}))
    path = tmp_path / "catalog.db"
    conn = sqlite3.connect(path)
    refresh_database(data_dir, conn)
    conn.close()
    return path


def make_request(**changes: object) -> AgentRequest:
    fields = {
        "student": {"degree_level": "bachelor", "programs": ["tiny-bs"], "catalog_year": "2026-2027"},
        "semesters": 2,
        "start_term": "Fall 2026",
    } | changes
    return AgentRequest.model_validate(fields)


@pytest.fixture
def planner(db_path: Path, tmp_path: Path) -> PlannerTools:
    return PlannerTools(sqlite3.connect(db_path), make_request(), tmp_path / "plan.json")


# --- PlannerTools -------------------------------------------------------------------------------


def test_lookup_tools_are_wired(planner: PlannerTools) -> None:
    assert planner.call("get_program_requirements", {"program_id": "tiny-bs"})["program_id"] == "tiny-bs"
    assert [c["code"] for c in planner.call("search_catalog", {"query": "TEST"})["courses"]] == ["TEST101", "TEST102"]
    assert "error" not in planner.call("get_prerequisites", {"code": "TEST102"})
    assert "error" not in planner.call("get_forms", {"program_id": "tiny-bs"})


def test_unknown_tool_gets_an_error_naming_the_tools(planner: PlannerTools) -> None:
    error = planner.call("make_plan", {})["error"]
    assert "make_plan" in error
    assert all(tool["name"] in error for tool in TOOL_DEFINITIONS)


def test_accepted_plan_is_saved(planner: PlannerTools) -> None:
    result = planner.call("check_plan", GOOD_PLAN)

    assert result["requirements_met"] is True
    assert json.loads(planner.plan_path.read_text()) == GOOD_PLAN


def test_failing_plan_is_still_saved(planner: PlannerTools) -> None:
    # Saved even when requirements are not met: the loop returns it so the page can draw it.
    half = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2027", "courses": []}]}
    result = planner.call("check_plan", half)

    assert result["requirements_met"] is False
    assert json.loads(planner.plan_path.read_text()) == half


def test_rejected_plan_does_not_replace_the_saved_one(planner: PlannerTools) -> None:
    planner.call("check_plan", GOOD_PLAN)
    result = planner.call("check_plan", {"semesters": "not a list"})

    assert "error" in result
    assert json.loads(planner.plan_path.read_text()) == GOOD_PLAN


def test_no_plan_file_until_a_plan_is_accepted(planner: PlannerTools) -> None:
    planner.call("search_catalog", {"query": "TEST"})
    planner.call("check_plan", {"semesters": [{"label": "Fall 1999", "courses": []}]})

    assert not planner.plan_path.exists()


@pytest.mark.parametrize(
    "semesters",
    [
        [{"label": "Fall 2026", "courses": ["TEST101", "TEST102"]}],
        [{"label": "Spring 2027", "courses": ["TEST101"]}, {"label": "Fall 2026", "courses": ["TEST102"]}],
        [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2028", "courses": ["TEST102"]}],
    ],
)
def test_wrong_labels_are_rejected(planner: PlannerTools, semesters: list) -> None:
    result = planner.call("check_plan", {"semesters": semesters})

    assert json.dumps(LABELS) in result["error"]
    assert not planner.plan_path.exists()


def test_check_plan_uses_the_students_overrides(db_path: Path, tmp_path: Path) -> None:
    # The record and overrides come from the request file, never from the model's input.
    student = {
        "degree_level": "bachelor",
        "programs": ["tiny-bs"],
        "catalog_year": "2026-2027",
        "completed_courses": [{"code": "TEST101", "credits": 3.0, "term": "transfer"}],
    }
    planner = PlannerTools(sqlite3.connect(db_path), make_request(student=student), tmp_path / "plan.json")
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST102"]}, {"label": "Spring 2027", "courses": []}]}

    assert planner.call("check_plan", plan)["requirements_met"] is True


# --- the real server over MCP -------------------------------------------------------------------


def run_session(db_path: Path, tmp_path: Path, calls: list[tuple[str, dict]]) -> tuple[list[str], list]:
    request_path = tmp_path / "request.json"
    request_path.write_text(make_request().model_dump_json(by_alias=True))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "degree_planner_backend.agent.mcp_server",
              "--db", str(db_path), "--request", str(request_path), "--plan", str(tmp_path / "plan.json")],
    )

    async def session() -> tuple[list[str], list]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listed = await client.list_tools()
                results = [await client.call_tool(name, arguments) for name, arguments in calls]
                return [tool.name for tool in listed.tools], results

    return asyncio.run(session())


def test_server_lists_the_five_tools(db_path: Path, tmp_path: Path) -> None:
    names, _ = run_session(db_path, tmp_path, [])

    assert names == ["search_catalog", "get_prerequisites", "get_program_requirements", "get_forms", "check_plan"]


def test_server_runs_tools_and_saves_the_plan(db_path: Path, tmp_path: Path) -> None:
    _, [lookup, unknown, check] = run_session(
        db_path, tmp_path,
        [("search_catalog", {"query": "TEST"}), ("make_plan", {}), ("check_plan", GOOD_PLAN)],
    )

    assert lookup.is_error is False
    assert len(json.loads(lookup.content[0].text)["courses"]) == 2
    assert unknown.is_error is True
    assert check.is_error is False
    assert json.loads(check.content[0].text)["requirements_met"] is True
    assert json.loads((tmp_path / "plan.json").read_text()) == GOOD_PLAN


def test_server_opens_the_catalog_read_only(db_path: Path, tmp_path: Path) -> None:
    run_session(db_path, tmp_path, [("search_catalog", {"query": "TEST"})])
    before = db_path.stat().st_mtime_ns
    run_session(db_path, tmp_path, [("check_plan", GOOD_PLAN)])

    assert db_path.stat().st_mtime_ns == before
