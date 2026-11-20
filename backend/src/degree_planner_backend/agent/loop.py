"""Agent loop: plan, check, revise (plans/AGENT-PLAN.md, task "Agent loop").

Takes an AgentRequest (request_models.py), lets the model call the tools in tools.py until
check_plan says the plan meets the requirements or the step limit is reached, and returns an
AgentResponse: status "ok" with a validated plan, or "cannot_work" with the problems.
The format both ways is docs/agent-request-format.md.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Callable

import anthropic

from degree_planner_backend import validator
from degree_planner_backend.agent import tools
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

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000  # per model call; non-streaming, so kept under the SDK's request timeout
# Recommended starting point for multistep tool use on Sonnet 5.5; tune with the eval like STEP_LIMIT.
EFFORT = "medium"
# On a refusal, the API retries the same request on a fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Most model calls one request may make (Usage.steps) before the loop returns "cannot_work".
# Placeholder set generously so it does not decide the outcome yet; to be tuned from the
# usage.steps of real runs (Example 1 first, then the eval runner) and recorded in DECISIONS.md.
STEP_LIMIT = 25

# The same for every request, so it can be cached; the student's details and the semester labels
# go in the first user message instead. The loop, not the model, decides "ok" or "cannot_work"
# from the last check_plan result; the model's final message becomes the explanation.
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


# Tool order is fixed so the cached prefix (tools, then system prompt) is the same on every call.
TOOL_DEFINITIONS = [
    tools.SEARCH_CATALOG_TOOL,
    tools.GET_PREREQUISITES_TOOL,
    tools.GET_PROGRAM_REQUIREMENTS_TOOL,
    tools.GET_FORMS_TOOL,
    tools.CHECK_PLAN_TOOL,
]
_LOOKUP_HANDLERS: dict[str, Callable[[sqlite3.Connection, dict[str, Any]], tools.ToolResult]] = {
    "search_catalog": tools.search_catalog,
    "get_prerequisites": tools.get_prerequisites,
    "get_program_requirements": tools.get_program_requirements,
    "get_forms": tools.get_forms,
}

NO_PLAN_PROBLEM = "The agent never sent a plan that check_plan could read."
NOT_MET_PROBLEM = "The plan does not meet every requirement of the student's programs yet."
STEP_LIMIT_PROBLEM = f"The agent stopped after {STEP_LIMIT} steps without finishing."
CUT_OFF_PROBLEM = "The agent's reply was cut off before it finished."
REFUSED_PROBLEM = "The model declined to answer this request."
EMPTY_EXPLANATION = "The agent finished without writing an explanation."


def run_agent(
    connection: sqlite3.Connection,
    request: AgentRequest,
    client: anthropic.Anthropic | None = None,
) -> AgentResponse:
    """Plan for the student in request and return the checked result.

    client is for tests; by default one is made from the environment (ANTHROPIC_API_KEY).
    API errors (network, rate limit after the SDK's retries, bad key) are raised, not turned
    into "cannot_work": they are a server problem, not something about the student's plan.
    """
    client = client or anthropic.Anthropic()
    labels = request.semester_labels()
    context = tools.StudentContext(
        student=request.student,
        overrides=frozenset((o.type, o.code) for o in request.overrides),
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": _first_message(request, labels)}]

    input_tokens = output_tokens = steps = 0
    last_plan_input: dict[str, Any] | None = None  # the last check_plan input that check_plan accepted
    final_text = ""
    stop_problem: str | None = None

    while True:
        if steps == STEP_LIMIT:
            stop_problem = STEP_LIMIT_PROBLEM
            break
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
            output_config={"effort": EFFORT},
            # Caches everything up to the last message, so each step pays full price only for what is new.
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        steps += 1
        usage = response.usage
        # All input counts, cached or not, so the eval's token numbers are the whole request.
        input_tokens += (
            usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0)
        )
        output_tokens += usage.output_tokens
        # The whole content goes back, thinking blocks included, as the API requires.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            stop_problem = REFUSED_PROBLEM
            break
        if response.stop_reason == "max_tokens":
            stop_problem = CUT_OFF_PROBLEM
            break

        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            parts = [block.text.strip() for block in response.content if block.type == "text"]
            final_text = "\n\n".join(part for part in parts if part)
            break

        results = []
        for block in tool_uses:
            result = _run_tool(connection, context, labels, block.name, block.input)
            if block.name == "check_plan" and "error" not in result:
                last_plan_input = block.input
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
                "is_error": "error" in result,
            })
        # Every result goes back in one message, so the model keeps asking for several tools at once.
        messages.append({"role": "user", "content": results})

    usage_total = Usage(input_tokens=input_tokens, output_tokens=output_tokens, steps=steps)
    return _build_response(connection, context, last_plan_input, final_text, stop_problem, usage_total)


def _first_message(request: AgentRequest, labels: list[str]) -> str:
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


def _run_tool(
    connection: sqlite3.Connection,
    context: tools.StudentContext,
    labels: list[str],
    name: str,
    tool_input: Any,
) -> tools.ToolResult:
    if name == "check_plan":
        # Checked before the tool runs, so the model fixes its labels now instead of the plan
        # failing at the end for not answering the request.
        sent = tool_input.get("semesters") if isinstance(tool_input, dict) else None
        if isinstance(sent, list):
            sent_labels = [item.get("label") if isinstance(item, dict) else None for item in sent]
            if sent_labels != labels:
                return {"error": f"semesters must use exactly these labels, in this order: {json.dumps(labels)}."}
        return tools.check_plan(connection, tool_input, context)
    handler = _LOOKUP_HANDLERS.get(name)
    if handler is None:
        names = ", ".join(tool["name"] for tool in TOOL_DEFINITIONS)
        return {"error": f"there is no tool named {name!r}; the tools are {names}."}
    return handler(connection, tool_input)


def _build_response(
    connection: sqlite3.Connection,
    context: tools.StudentContext,
    plan_input: dict[str, Any] | None,
    final_text: str,
    stop_problem: str | None,
    usage: Usage,
) -> AgentResponse:
    """Rebuild and validate the last plan the model sent, and decide the status from that."""
    explanation = final_text[:EXPLANATION_MAX] if final_text else EMPTY_EXPLANATION
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
