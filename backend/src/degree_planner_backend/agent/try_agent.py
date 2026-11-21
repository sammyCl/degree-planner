"""Run the real agent on one request file and print what it returned.

    uv run try-agent ../docs/agent-request.sample.json
    uv run try-agent REQUEST.json --db other.db --json response.json

This calls Claude Code for real, on the signed-in Claude Code account, so it uses plan usage.
The automated tests never do; this is for trying an example by hand after changing planner.md.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse
from degree_planner_backend.db import DB_PATH


def summarize(response: AgentResponse, seconds: float) -> str:
    usage = response.usage
    lines = [
        f"status: {response.status}",
        f"steps: {usage.steps} of {loop.STEP_LIMIT}   tokens: {usage.input_tokens} in, "
        f"{usage.output_tokens} out   time: {seconds:.0f}s",
    ]
    if response.problems:
        lines.append("problems:")
        lines += [f"  - {problem}" for problem in response.problems]
    if response.plan is None:
        lines.append("plan: none")
    else:
        summary = response.plan.summary
        lines.append(
            f"plan: {summary.total_credits:g} of {summary.total_credits_required:g} credits, "
            f"requirements met: {'yes' if summary.requirements_met else 'no'}"
        )
        for semester in response.plan.semesters:
            codes = ", ".join(course.code for course in semester.courses) or "(none)"
            lines.append(f"  {semester.label} ({semester.total_credits:g} cr): {codes}")
        open_flags = [flag for flag in response.plan.flags if not flag.overridden]
        if open_flags:
            lines.append("flags:")
            lines += [f"  - [{flag.severity}] {flag.message}" for flag in open_flags]
    lines += ["explanation:", response.explanation]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="try-agent", description="Run the agent on one request and print the result.")
    parser.add_argument("request", type=Path, help="an agent request JSON file (docs/agent-request-format.md)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"catalog database (default: {DB_PATH.name})")
    parser.add_argument("--json", type=Path, metavar="FILE", help="also save the full response as JSON here")
    args = parser.parse_args(argv)

    try:
        request = AgentRequest.model_validate_json(args.request.read_text())
    except OSError as exc:
        print(f"cannot read {args.request}: {exc.strerror}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"{args.request} is not a valid agent request:\n{exc}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"no database at {args.db}; load the data first (uv run load-data)", file=sys.stderr)
        return 2

    connection = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
    started = time.monotonic()
    try:
        response = loop.run_agent(connection, request)
    except loop.ClaudeCodeError as exc:
        print(f"Claude Code could not run: {exc}. Is it installed and signed in (run `claude` once)?", file=sys.stderr)
        return 1
    finally:
        connection.close()

    print(summarize(response, time.monotonic() - started))
    if args.json:
        # by_alias: prerequisite edges are written as "from", not "from_" (BUG-031).
        args.json.write_text(response.model_dump_json(by_alias=True, indent=2))
        print(f"\nfull response saved to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
