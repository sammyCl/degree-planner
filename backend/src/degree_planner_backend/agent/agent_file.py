"""Reads the agent definition file (planner.md): frontmatter settings plus the system prompt.

The format is the one Claude Code agent files use (P3's .claude/agents/*.md), limited to what the
loop needs, and read strictly: an unknown key, a missing one, or a bad value is an error at
startup rather than an agent that quietly behaves differently.

    ---
    # comment lines are allowed in the frontmatter
    name: planner
    description: one line
    model: claude-sonnet-5-5
    effort: medium
    maxTurns: 25
    tools: search_catalog, check_plan
    ---
    The system prompt, word for word.

The frontmatter is parsed by hand (one `key: value` per line), so no YAML library is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from degree_planner_backend.agent.mcp_server import TOOL_DEFINITIONS

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
MAX_TURNS_LIMIT = 100
_REQUIRED = ("name", "model", "effort", "maxTurns", "tools")
_KNOWN = _REQUIRED + ("description",)
_FENCE = "---"


class AgentFileError(ValueError):
    pass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    model: str
    effort: str
    max_turns: int
    tools: tuple[str, ...]
    system_prompt: str


def load_agent(path: Path) -> AgentSpec:
    return parse_agent(path.read_text(encoding="utf-8"), source=str(path))


def parse_agent(text: str, source: str = "agent file") -> AgentSpec:
    lines = text.split("\n")
    if not lines or lines[0].strip() != _FENCE:
        raise AgentFileError(f"{source}: must start with a '---' line")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FENCE)
    except StopIteration:
        raise AgentFileError(f"{source}: the frontmatter has no closing '---' line") from None

    fields: dict[str, str] = {}
    for number, line in enumerate(lines[1:end], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise AgentFileError(f"{source}, line {number}: expected 'key: value'")
        if key not in _KNOWN:
            raise AgentFileError(f"{source}, line {number}: unknown key {key!r}; the keys are {', '.join(_KNOWN)}")
        if key in fields:
            raise AgentFileError(f"{source}, line {number}: {key!r} is given twice")
        if not value:
            raise AgentFileError(f"{source}, line {number}: {key!r} has no value")
        fields[key] = value

    missing = [key for key in _REQUIRED if key not in fields]
    if missing:
        raise AgentFileError(f"{source}: missing {', '.join(missing)}")

    if fields["effort"] not in EFFORT_LEVELS:
        raise AgentFileError(f"{source}: effort must be one of {', '.join(EFFORT_LEVELS)}, not {fields['effort']!r}")

    turns = fields["maxTurns"]
    if not (turns.isascii() and turns.isdigit() and 1 <= int(turns) <= MAX_TURNS_LIMIT):
        raise AgentFileError(f"{source}: maxTurns must be a whole number from 1 to {MAX_TURNS_LIMIT}, not {turns!r}")

    available = [tool["name"] for tool in TOOL_DEFINITIONS]
    tools = tuple(name.strip() for name in fields["tools"].split(","))
    for name in tools:
        if name not in available:
            raise AgentFileError(
                f"{source}: tool {name!r} is not one the planner server offers ({', '.join(available)})"
            )
    if len(set(tools)) != len(tools):
        raise AgentFileError(f"{source}: a tool is listed twice")

    # Everything after the closing line, exactly as written.
    system_prompt = "\n".join(lines[end + 1:])
    if not system_prompt.strip():
        raise AgentFileError(f"{source}: the system prompt below the frontmatter is empty")

    return AgentSpec(
        name=fields["name"],
        description=fields.get("description", ""),
        model=fields["model"],
        effort=fields["effort"],
        max_turns=int(turns),
        tools=tools,
        system_prompt=system_prompt,
    )
