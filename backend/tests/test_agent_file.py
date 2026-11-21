"""Tests for reading the agent definition file (agent/agent_file.py and agent/planner.md)."""

import pytest

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.agent_file import AgentFileError, load_agent, parse_agent

GOOD = """\
---
# a comment
name: planner
description: Plans degrees.
model: claude-sonnet-5-5
effort: medium
maxTurns: 25
tools: search_catalog, check_plan
---
Line one of the prompt.

Line three: with a colon, and a --- inside.
"""


def with_line(old: str, new: str) -> str:
    assert old in GOOD
    return GOOD.replace(old, new)


def test_good_file_is_read() -> None:
    agent = parse_agent(GOOD)

    assert agent.name == "planner"
    assert agent.description == "Plans degrees."
    assert agent.model == "claude-sonnet-5-5"
    assert agent.effort == "medium"
    assert agent.max_turns == 25
    assert agent.tools == ("search_catalog", "check_plan")
    assert agent.system_prompt == "Line one of the prompt.\n\nLine three: with a colon, and a --- inside.\n"


def test_description_is_optional() -> None:
    assert parse_agent(with_line("description: Plans degrees.\n", "")).description == ""


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: planner\n", "must start with a '---' line"),
        ("---\nname: planner\n", "no closing '---'"),
        (with_line("name: planner", "name planner"), "expected 'key: value'"),
        (with_line("name: planner", "temperature: 0.2"), "unknown key 'temperature'"),
        (with_line("name: planner", "name: planner\nname: other"), "given twice"),
        (with_line("model: claude-sonnet-5-5", "model:"), "'model' has no value"),
        (with_line("maxTurns: 25\n", ""), "missing maxTurns"),
        (with_line("effort: medium", "effort: extreme"), "effort must be one of"),
        (with_line("maxTurns: 25", "maxTurns: 0"), "maxTurns must be a whole number"),
        (with_line("maxTurns: 25", "maxTurns: 101"), "maxTurns must be a whole number"),
        (with_line("maxTurns: 25", "maxTurns: 2.5"), "maxTurns must be a whole number"),
        (with_line("maxTurns: 25", "maxTurns: ２５"), "maxTurns must be a whole number"),
        (with_line("tools: search_catalog, check_plan", "tools: search_catalog, Bash"), "tool 'Bash' is not one"),
        (with_line("tools: search_catalog, check_plan", "tools: search_catalog,, check_plan"), "tool '' is not one"),
        (with_line("tools: search_catalog, check_plan", "tools: check_plan, check_plan"), "listed twice"),
        (GOOD.split("---\nLine one")[0] + "---\n   \n", "system prompt below the frontmatter is empty"),
    ],
)
def test_bad_file_is_rejected(text: str, message: str) -> None:
    with pytest.raises(AgentFileError, match=message):
        parse_agent(text)


def test_error_names_the_file_and_line(tmp_path) -> None:
    path = tmp_path / "broken.md"
    path.write_text(with_line("effort: medium", "efort: medium"))
    with pytest.raises(AgentFileError, match=r"broken\.md, line 6: unknown key 'efort'"):
        load_agent(path)


# --- the real planner.md ------------------------------------------------------------------------


def test_planner_file_is_what_the_loop_uses() -> None:
    agent = load_agent(loop.AGENT_FILE)

    assert loop.AGENT_FILE.name == "planner.md"
    assert loop.SYSTEM_PROMPT == agent.system_prompt
    assert loop.MODEL == agent.model == "claude-sonnet-5-5"
    assert loop.EFFORT == agent.effort
    assert loop.STEP_LIMIT == agent.max_turns
    assert loop.ALLOWED_TOOLS == [f"mcp__planner__{name}" for name in agent.tools]


def test_planner_file_gives_the_agent_all_five_tools() -> None:
    assert load_agent(loop.AGENT_FILE).tools == (
        "search_catalog", "get_prerequisites", "get_program_requirements", "get_forms", "check_plan",
    )


def test_planner_prompt_keeps_the_rules_the_plan_asks_for() -> None:
    # AGENT-PLAN.md, Agent loop: the student stays in the loop; never invent courses.
    prompt = load_agent(loop.AGENT_FILE).system_prompt

    assert "Never invent a course code" in prompt
    assert "Never decide an exception for the student" in prompt
    assert "4,000 characters" in prompt  # EXPLANATION_MAX
