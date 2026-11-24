"""The chatbot's plan-editing tools (docs/chat-format.md, plans/AGENT-PLAN.md "Chat logic").

The chatbot starts from the student's plan on the board and changes only what the student asks
for, one small edit at a time, instead of sending a whole new plan the way the planner does with
check_plan. Every tool answers with the same result check_plan gives (tools.check_plan on the
working plan), so the model always sees what an edit broke or fixed.

ChatSession is plain Python, so it can be tested without MCP; mcp_server.py serves it in chat mode.
The catalog lookups (search_catalog, get_prerequisites, get_program_requirements, get_forms) are
the planner's, unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from degree_planner_backend.agent import tools
from degree_planner_backend.agent.chat_models import ChatRequest
from degree_planner_backend.agent.tools import (
    CATALOG_UNAVAILABLE,
    COURSES_PER_SEMESTER_MAX,
    OVERRIDABLE_FLAG_TYPES,
    ToolResult,
    _BadInput,
    _clean_stored_code,
    _COURSE_CODE,
    _is_valid_text,
    _normalize_code,
)

logger = logging.getLogger(__name__)

EXCEPTION_TYPE = "exception_claimed"
assert EXCEPTION_TYPE in OVERRIDABLE_FLAG_TYPES

# Most credits in one semester without extra approval: 18 undergraduate, 15 graduate (2026-2027
# Graduate Catalog). The validator does not check this, so the chat tools report it, worked out
# in code, and the model never adds credits itself. A combined BS+MS plan uses the undergraduate
# limit here; chat.md tells the model about its graduate semesters.
CREDIT_LIMIT_UNDERGRADUATE = 18
CREDIT_LIMIT_GRADUATE = 15
_GRADUATE_LEVELS = {"master", "phd"}


def credit_limit(degree_level: str) -> int:
    return CREDIT_LIMIT_GRADUATE if degree_level in _GRADUATE_LEVELS else CREDIT_LIMIT_UNDERGRADUATE


_RESULT_NOTE = (
    "Returns the same result as check_plan for the whole plan after the change: requirements_met, "
    "total_credits, total_credits_required, semesters, errors, warnings, unknown_courses and open_exceptions. "
    "Each semester also has credit_limit (the most credits it may hold) and room (credits left under the "
    "limit, negative when over) and completed_on_board (courses the board shows as already completed: not in "
    "the plan and not counted in room), and semesters_over_credit_limit lists the semesters over their limit: "
    "use these numbers instead of adding credits yourself. A course fits in a semester only if its credits are "
    "at most that semester's room. An edit that is refused returns only an error and changes nothing; call "
    "get_current_plan if you need the numbers again."
)
_CODE = {"type": "string", "description": "Course code such as 'CSCI400'."}
_LABEL = {"type": "string", "description": "A semester label from the plan, such as 'Fall 2027'."}

GET_CURRENT_PLAN_TOOL: dict[str, Any] = {
    "name": "get_current_plan",
    "description": (
        "Show the student's plan as it stands in this conversation, including your edits so far, checked "
        "against the rules. Call it first to see the plan before you change anything. " + _RESULT_NOTE
    ),
    "input_schema": {"type": "object", "properties": {}},
}

MOVE_COURSE_TOOL: dict[str, Any] = {
    "name": "move_course",
    "description": (
        "Move a course already in the plan to another semester of the plan. Use from_label only when the "
        "course is planned in more than one semester. A move can break a prerequisite (the course now "
        "comes before what it needs, or after a course that needs it); the result shows it. " + _RESULT_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {"code": _CODE, "to_label": _LABEL, "from_label": _LABEL},
        "required": ["code", "to_label"],
    },
}

REPLACE_COURSE_TOOL: dict[str, Any] = {
    "name": "replace_course",
    "description": (
        "Replace a course in the plan with another course in the same semester, for example one elective "
        "with another. new_code must be a real catalog course (find it with search_catalog) that is not "
        "already planned or completed. Check with get_prerequisites that the new course's prerequisites are "
        "met. " + _RESULT_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {"old_code": _CODE, "new_code": _CODE, "label": _LABEL},
        "required": ["old_code", "new_code"],
    },
}

ADD_COURSE_TOOL: dict[str, Any] = {
    "name": "add_course",
    "description": (
        "Add a catalog course to one semester of the plan. The course must not already be planned or "
        "completed. " + _RESULT_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {"code": _CODE, "label": _LABEL},
        "required": ["code", "label"],
    },
}

REMOVE_COURSE_TOOL: dict[str, Any] = {
    "name": "remove_course",
    "description": (
        "Remove a course from the plan. Use label only when the course is planned in more than one semester. "
        "Removing a required course leaves a requirement unmet; the result shows it. " + _RESULT_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {"code": _CODE, "label": _LABEL},
        "required": ["code"],
    },
}

ACCEPT_EXCEPTION_TOOL: dict[str, Any] = {
    "name": "accept_exception",
    "description": (
        "Accept the exception for a course in open_exceptions, because the student told you in this "
        "conversation that they were granted it (for example placement or instructor approval). Never call "
        "it on your own judgment or because it would make the plan pass. Only exception_claimed flags can be "
        "accepted; a broken prerequisite, an unmet requirement or a course substitution cannot. The student "
        "sees every exception you accept and decides whether to apply it. " + _RESULT_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {"code": _CODE},
        "required": ["code"],
    },
}

CHAT_EDIT_TOOLS = [
    GET_CURRENT_PLAN_TOOL,
    MOVE_COURSE_TOOL,
    REPLACE_COURSE_TOOL,
    ADD_COURSE_TOOL,
    REMOVE_COURSE_TOOL,
    ACCEPT_EXCEPTION_TOOL,
]


def _code_field(tool_input: dict[str, Any], name: str) -> str:
    value = tool_input.get(name)
    if not isinstance(value, str) or not _is_valid_text(value):
        raise _BadInput(f"{name} must be a course code such as 'CSCI400'.")
    code = _normalize_code(unicodedata.normalize("NFKC", value).strip())
    if not _COURSE_CODE.fullmatch(code):
        # Not echoed back: it can be long or carry text aimed at the model.
        raise _BadInput(f"{name} is not a course code such as 'CSCI400' (3-4 letters, 3 digits, optional letter suffix).")
    return code


class ChatSession:
    """The working plan for one chat request: semesters of course codes, the overrides, and the
    exceptions accepted in this conversation. Saved to state_path after every accepted edit, for
    the loop to rebuild and validate once Claude Code is done."""

    def __init__(self, connection: sqlite3.Connection, request: ChatRequest, state_path: Path) -> None:
        self.connection = connection
        self.student = request.plan.student
        self.labels = request.semester_labels()
        # Only planned courses: completed ones come from the student's record, not the board.
        self.semesters: list[list[str]] = [
            [_clean_stored_code(c.code) for c in semester.courses if c.status == "planned"]
            for semester in request.plan.semesters
        ]
        # Completed rows on the board: not in the plan, but shown to the model so it does not plan
        # into a semester that is already done.
        self.completed_on_board: list[list[str]] = [
            [_clean_stored_code(c.code) for c in semester.courses if c.status == "completed"]
            for semester in request.plan.semesters
        ]
        self.overrides: set[tuple[str, str]] = {(o.type, o.code) for o in request.overrides}
        self.accepted: list[str] = []
        self.state_path = state_path

    # --- dispatch ---------------------------------------------------------------------------

    def call(self, name: str, tool_input: Any) -> ToolResult:
        handler = {
            "get_current_plan": self._get_current_plan,
            "move_course": self._move_course,
            "replace_course": self._replace_course,
            "add_course": self._add_course,
            "remove_course": self._remove_course,
            "accept_exception": self._accept_exception,
        }.get(name)
        if handler is None:
            return {"error": f"there is no chat tool named {name!r}."}
        if not isinstance(tool_input, dict):
            return {"error": f"tool input must be a JSON object with the fields in the {name} schema."}
        try:
            return handler(tool_input)
        except _BadInput as exc:
            return {"error": str(exc)}
        except Exception:
            # A tool must never raise into the loop; the details go to the log, not the model.
            logger.exception("%s: unexpected error", name)
            return {"error": CATALOG_UNAVAILABLE}

    # --- tools ------------------------------------------------------------------------------

    def _get_current_plan(self, _tool_input: dict[str, Any]) -> ToolResult:
        return self._check()

    def _move_course(self, tool_input: dict[str, Any]) -> ToolResult:
        code = _code_field(tool_input, "code")
        to_index = self._label_index(tool_input, "to_label", required=True)
        from_index = self._find(code, self._label_index(tool_input, "from_label", required=False))
        if from_index == to_index:
            raise _BadInput(f"{code} is already in {self.labels[to_index]}.")
        edited = self._copy()
        edited[from_index].remove(code)
        edited[to_index].append(code)
        return self._apply(edited, added=(code, to_index), removed=(code, from_index))

    def _replace_course(self, tool_input: dict[str, Any]) -> ToolResult:
        old = _code_field(tool_input, "old_code")
        new = _code_field(tool_input, "new_code")
        if old == new:
            raise _BadInput("old_code and new_code are the same course.")
        index = self._find(old, self._label_index(tool_input, "label", required=False))
        edited = self._copy()
        position = edited[index].index(old)
        edited[index][position] = new
        return self._apply(edited, added=(new, index), removed=(old, index))

    def _add_course(self, tool_input: dict[str, Any]) -> ToolResult:
        code = _code_field(tool_input, "code")
        index = self._label_index(tool_input, "label", required=True)
        if len(self.semesters[index]) >= COURSES_PER_SEMESTER_MAX:
            raise _BadInput(f"{self.labels[index]} already has {COURSES_PER_SEMESTER_MAX} courses, the most a semester can hold.")
        edited = self._copy()
        edited[index].append(code)
        return self._apply(edited, added=(code, index))

    def _remove_course(self, tool_input: dict[str, Any]) -> ToolResult:
        code = _code_field(tool_input, "code")
        index = self._find(code, self._label_index(tool_input, "label", required=False))
        edited = self._copy()
        edited[index].remove(code)
        return self._apply(edited, removed=(code, index))

    def _accept_exception(self, tool_input: dict[str, Any]) -> ToolResult:
        code = _code_field(tool_input, "code")
        open_exceptions = self._check().get("open_exceptions", [])
        if code not in open_exceptions:
            shown = ", ".join(open_exceptions) if open_exceptions else "none"
            raise _BadInput(
                f"{code} has no open exception to accept; open_exceptions is {shown}. Only exception_claimed "
                "flags can be accepted."
            )
        self.overrides.add((EXCEPTION_TYPE, code))
        self.accepted.append(code)
        self._save()
        return self._check()

    # --- helpers ----------------------------------------------------------------------------

    def _label_index(self, tool_input: dict[str, Any], name: str, *, required: bool) -> int | None:
        value = tool_input.get(name)
        if value is None and not required:
            return None
        if isinstance(value, str) and value in self.labels:
            return self.labels.index(value)
        raise _BadInput(f"{name} must be one of the plan's semesters: {json.dumps(self.labels)}.")

    def _find(self, code: str, index: int | None) -> int:
        """The semester holding code: the given one, or the only one."""
        if index is not None:
            if code not in self.semesters[index]:
                raise _BadInput(f"{code} is not planned in {self.labels[index]}.")
            return index
        found = [i for i, codes in enumerate(self.semesters) if code in codes]
        if not found:
            raise _BadInput(f"{code} is not in the plan. Call get_current_plan to see the courses planned.")
        if len(found) > 1:
            shown = ", ".join(self.labels[i] for i in found)
            raise _BadInput(f"{code} is planned in more than one semester ({shown}); say which one.")
        return found[0]

    def _copy(self) -> list[list[str]]:
        return [list(codes) for codes in self.semesters]

    def _context(self) -> tools.StudentContext:
        return tools.StudentContext(student=self.student, overrides=frozenset(self.overrides))

    def _tool_input(self, semesters: list[list[str]]) -> dict[str, Any]:
        return {"semesters": [{"label": label, "courses": codes} for label, codes in zip(self.labels, semesters)]}

    def _check(self, semesters: list[list[str]] | None = None) -> ToolResult:
        result = tools.check_plan(self.connection, self._tool_input(self.semesters if semesters is None else semesters), self._context())
        return self._with_credit_room(result)

    def _with_credit_room(self, result: ToolResult) -> ToolResult:
        """Adds each semester's credit_limit, room and completed_on_board, and the semesters over
        their limit."""
        if "error" in result:
            return result
        limit = credit_limit(self.student.degree_level)
        over = []
        for semester, completed in zip(result["semesters"], self.completed_on_board):
            credits = semester["credits"]
            semester["credit_limit"] = limit
            semester["room"] = round(limit - credits, 2)
            semester["completed_on_board"] = completed
            if credits > limit:
                over.append(semester["label"])
        result["semesters_over_credit_limit"] = over
        return result

    def _apply(
        self,
        edited: list[list[str]],
        *,
        added: tuple[str, int] | None = None,
        removed: tuple[str, int] | None = None,
    ) -> ToolResult:
        """Keep the edit only when it does exactly what was asked: the added course is really kept
        where it was put (not unknown, already completed or already planned), and no other course
        the plan kept before is dropped by it (build_plan keeps the first of a repeated course, so
        adding one earlier would silently drop the later one). Otherwise undo it and say why."""
        before = self._check()
        result = self._check(edited)
        if "error" in before or "error" in result:
            return result if "error" in result else before
        kept_after = [semester["courses"] for semester in result["semesters"]]
        if added is not None:
            code, index = added
            # An edit never adds and removes the same course in one semester (a move to its own
            # semester and a replace with itself are refused above), so these two checks suffice.
            if code in before["semesters"][index]["courses"]:
                # The validator keeps one copy per semester, so the edit would do nothing (an add)
                # or quietly turn into a removal (a replace or a move).
                raise _BadInput(f"Not changed: {code} is already planned in {self.labels[index]}.")
            if code not in kept_after[index]:
                raise _BadInput(f"Not changed: {self._reason(result, code, index)}")
        for index, semester in enumerate(before["semesters"]):
            for code in semester["courses"]:
                if (code, index) != removed and code not in kept_after[index]:
                    raise _BadInput(
                        f"Not changed: the edit would drop {code} from {self.labels[index]}. "
                        f"{self._reason(result, code, index)}"
                    )
        self.semesters = edited
        self._save()
        return result

    def _reason(self, result: ToolResult, code: str, index: int) -> str:
        reasons = [issue["message"] for issue in result["errors"] + result["warnings"] if issue.get("course") == code]
        return reasons[0] if reasons else f"{code} could not be planned in {self.labels[index]}."

    def state(self) -> dict[str, Any]:
        return self._tool_input(self.semesters) | {
            "accepted_overrides": [{"type": EXCEPTION_TYPE, "code": code} for code in self.accepted],
        }

    def _save(self) -> None:
        # Written to a temporary file and renamed, so the loop never reads half a state.
        partial = self.state_path.with_name(self.state_path.name + ".partial")
        partial.write_text(json.dumps(self.state()))
        os.replace(partial, self.state_path)
