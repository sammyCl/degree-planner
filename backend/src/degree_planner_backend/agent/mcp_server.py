"""MCP server that gives Claude Code the planner's tools (the five in tools.py and submit_summary), or in chat mode
the chatbot's tools (the four catalog lookups and the six in chat_tools.py).

The agent loop (loop.py) runs `claude -p`, and Claude Code starts this server as a child process
for one request. Run as:

    python -m degree_planner_backend.agent.mcp_server --db DB --request REQUEST.json --plan PLAN.json [--mode chat]

--db       the SQLite catalog, opened read-only
--request  the AgentRequest (or in chat mode the ChatRequest), written by the loop: the student's
           record, overrides and semester labels come from here, never from the model
--plan     where the server saves the last check_plan input it accepted (in chat mode, the working
           plan and accepted exceptions after every accepted edit), for the loop to rebuild and
           validate once Claude Code is done
--mode     plan (the default) or chat
--trace    chat mode only, optional: append one JSON line per tool call here (the tool, its input,
           and whether it worked), so a run can be checked afterwards

Only stderr is used for logging: stdout carries the MCP messages.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from degree_planner_backend.agent import tools
from degree_planner_backend.agent.chat_models import ChatRequest
from degree_planner_backend.agent.chat_tools import CHAT_EDIT_TOOLS, ChatSession
from degree_planner_backend.agent.request_models import SUMMARY_ITEM_MAX, SUMMARY_ITEMS_MAX, AgentRequest

logger = logging.getLogger(__name__)

SERVER_NAME = "planner"

SUBMIT_SUMMARY_TOOL: dict[str, Any] = {
    "name": "submit_summary",
    "description": (
        "Call once at the very end, after your last check_plan and before your final message, to hand "
        "back two short lists for the student's planner page. choices: each choice you made where the "
        "requirements left it open, such as which elective fills a group or which semester a course "
        "went in when either would work, one per item. notes: each thing the student should confirm "
        "with their advisor or the department, such as an approval, a course offered only some terms, "
        "or a catalog year the data comes from, one per item. Write each item as one or two plain "
        "sentences for the student, with no tool or field names; use [] when there is nothing. "
        f"At most {SUMMARY_ITEMS_MAX} items in each list and {SUMMARY_ITEM_MAX} characters in each item. "
        "A later check_plan clears what you sent, so call it again after any change to the plan."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "choices": {"type": "array", "items": {"type": "string"}, "maxItems": SUMMARY_ITEMS_MAX},
            "notes": {"type": "array", "items": {"type": "string"}, "maxItems": SUMMARY_ITEMS_MAX},
        },
        "required": ["choices", "notes"],
    },
}


def summary_path_for(plan_path: Path) -> Path:
    """Where submit_summary saves its lists: next to the plan file, in the run's temporary folder."""
    return plan_path.with_name("summary.json")

# Fixed order, so the tool list Claude Code sees is the same on every request.
TOOL_DEFINITIONS = [
    tools.SEARCH_CATALOG_TOOL,
    tools.GET_PREREQUISITES_TOOL,
    tools.GET_PROGRAM_REQUIREMENTS_TOOL,
    tools.GET_FORMS_TOOL,
    tools.CHECK_PLAN_TOOL,
    SUBMIT_SUMMARY_TOOL,
]
LOOKUP_TOOL_DEFINITIONS = TOOL_DEFINITIONS[:4]
# Chat mode: the catalog lookups and the edit tools, but not check_plan, so a small request cannot
# turn into a whole new plan.
CHAT_TOOL_DEFINITIONS = LOOKUP_TOOL_DEFINITIONS + CHAT_EDIT_TOOLS
_CHAT_EDIT_NAMES = frozenset(tool["name"] for tool in CHAT_EDIT_TOOLS)
# Longest tool name, input or error kept in one trace line.
TRACE_TEXT_MAX = 500
_LOOKUP_HANDLERS: dict[str, Callable[[sqlite3.Connection, dict[str, Any]], tools.ToolResult]] = {
    "search_catalog": tools.search_catalog,
    "get_prerequisites": tools.get_prerequisites,
    "get_program_requirements": tools.get_program_requirements,
    "get_forms": tools.get_forms,
}


def context_for(request: AgentRequest) -> tools.StudentContext:
    return tools.StudentContext(
        student=request.student,
        overrides=frozenset((o.type, o.code) for o in request.overrides),
    )


class PlannerTools:
    """Runs one tool call for one request. Plain Python, so it can be tested without MCP."""

    tool_definitions = TOOL_DEFINITIONS

    def __init__(self, connection: sqlite3.Connection, request: AgentRequest, plan_path: Path) -> None:
        self.connection = connection
        self.context = context_for(request)
        self.labels = request.semester_labels()
        self.plan_path = plan_path
        self.summary_path = summary_path_for(plan_path)

    def call(self, name: str, tool_input: Any) -> tools.ToolResult:
        if name == "check_plan":
            return self._check_plan(tool_input)
        if name == "submit_summary":
            return self._submit_summary(tool_input)
        handler = _LOOKUP_HANDLERS.get(name)
        if handler is None:
            names = ", ".join(tool["name"] for tool in TOOL_DEFINITIONS)
            return {"error": f"there is no tool named {name!r}; the tools are {names}."}
        return handler(self.connection, tool_input)

    def _check_plan(self, tool_input: Any) -> tools.ToolResult:
        # Checked before the tool runs, so the model fixes its labels now instead of the plan
        # failing at the end for not answering the request.
        sent = tool_input.get("semesters") if isinstance(tool_input, dict) else None
        if isinstance(sent, list):
            sent_labels = [item.get("label") if isinstance(item, dict) else None for item in sent]
            if sent_labels != self.labels:
                return {"error": f"semesters must use exactly these labels, in this order: {json.dumps(self.labels)}."}
        result = tools.check_plan(self.connection, tool_input, self.context)
        if "error" not in result:
            self._save_plan(tool_input)
            # A summary describes one plan: once the plan changes, it no longer fits.
            if self.summary_path.exists():
                self.summary_path.unlink()
                result["summary_cleared"] = "The plan changed, so the summary you sent was cleared: call submit_summary again at the end."
        return result

    def _submit_summary(self, tool_input: Any) -> tools.ToolResult:
        if not self.plan_path.exists():
            return {"error": "call check_plan with your plan first; submit_summary describes the plan check_plan accepted."}
        if not isinstance(tool_input, dict):
            return {"error": "tool input must be a JSON object with choices and notes, each a list of text."}
        lists: dict[str, list[str]] = {}
        for field in ("choices", "notes"):
            items = tool_input.get(field)
            if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                return {"error": f"{field} must be a list of text items (use [] when there is nothing)."}
            if len(items) > SUMMARY_ITEMS_MAX:
                return {"error": f"{field} may have at most {SUMMARY_ITEMS_MAX} items; keep the most important ones."}
            cleaned = []
            for item in items:
                if not tools._is_valid_text(item):
                    return {"error": f"an item in {field} contains characters that are not valid text."}
                text = tools.clean_text(item, SUMMARY_ITEM_MAX)
                if not text:
                    return {"error": f"an item in {field} is empty; leave it out instead."}
                cleaned.append(text)
            lists[field] = cleaned
        partial = self.summary_path.with_name(self.summary_path.name + ".partial")
        partial.write_text(json.dumps(lists))
        os.replace(partial, self.summary_path)
        return {"saved": True, "choices": len(lists["choices"]), "notes": len(lists["notes"])}

    def _save_plan(self, tool_input: dict[str, Any]) -> None:
        # Written to a temporary file and renamed, so the loop never reads half a plan.
        partial = self.plan_path.with_name(self.plan_path.name + ".partial")
        partial.write_text(json.dumps(tool_input))
        os.replace(partial, self.plan_path)


class ChatTools:
    """Runs one tool call for one chat request: the catalog lookups as the planner has them, and
    the edit tools on the request's working plan (ChatSession)."""

    tool_definitions = CHAT_TOOL_DEFINITIONS

    def __init__(self, connection: sqlite3.Connection, request: ChatRequest, state_path: Path,
                 trace_path: Path | None = None) -> None:
        self.connection = connection
        self.session = ChatSession(connection, request, state_path)
        self.trace_path = trace_path

    def call(self, name: str, tool_input: Any) -> tools.ToolResult:
        result = self._call(name, tool_input)
        if self.trace_path is not None:
            self._trace(name, tool_input, result)
        return result

    def _trace(self, name: str, tool_input: Any, result: tools.ToolResult) -> None:
        try:
            shown_input = json.dumps(tool_input, ensure_ascii=False)
        except (TypeError, ValueError):
            shown_input = repr(tool_input)
        error = result.get("error")
        line = {
            "tool": str(name)[:TRACE_TEXT_MAX],
            "input": shown_input[:TRACE_TEXT_MAX],
            "ok": error is None,
            "error": str(error)[:TRACE_TEXT_MAX] if error is not None else None,
        }
        try:
            with self.trace_path.open("a", encoding="utf-8") as trace:
                trace.write(json.dumps(line) + "\n")
        except OSError:
            # The trace is only for checking a run; it must never break a tool call.
            logger.exception("chat: could not write the tool trace")

    def _call(self, name: str, tool_input: Any) -> tools.ToolResult:
        if name in _CHAT_EDIT_NAMES:
            return self.session.call(name, tool_input)
        handler = _LOOKUP_HANDLERS.get(name)
        if handler is None:
            names = ", ".join(tool["name"] for tool in CHAT_TOOL_DEFINITIONS)
            return {"error": f"there is no tool named {name!r}; the tools are {names}."}
        return handler(self.connection, tool_input)


def build_server(planner: PlannerTools | ChatTools) -> Server:
    definitions = planner.tool_definitions

    async def list_tools(_context: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(name=tool["name"], description=tool["description"], inputSchema=tool["input_schema"])
                for tool in definitions
            ]
        )

    async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        result = planner.call(params.name, params.arguments if params.arguments is not None else {})
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(result))],
            isError="error" in result,
        )

    return Server(SERVER_NAME, on_list_tools=list_tools, on_call_tool=call_tool)


async def _serve(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server with the degree planner's tools")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--mode", choices=["plan", "chat"], default="plan")
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    # Read-only: no tool writes to the catalog, and a bug must not be able to change it.
    connection = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
    planner: PlannerTools | ChatTools
    if args.mode == "chat":
        planner = ChatTools(connection, ChatRequest.model_validate_json(args.request.read_text()), args.plan, args.trace)
    else:
        planner = PlannerTools(connection, AgentRequest.model_validate_json(args.request.read_text()), args.plan)
    asyncio.run(_serve(build_server(planner)))


if __name__ == "__main__":
    main()
