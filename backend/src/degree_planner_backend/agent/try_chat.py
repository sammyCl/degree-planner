"""Run the real chatbot on one chat request file and print what it returned.

    uv run try-chat ../docs/chat-request.sample.json
    uv run try-chat REQUEST.json --say "Can CSCI400 wait until Fall 2027?"
    uv run try-chat REQUEST.json --db other.db --json response.json

--say sets the student's last message, so one request file can be reused for many questions:
if the file's last message is the student's, --say replaces it; if it is the assistant's, --say
adds the student's message after it. Without --say the file must end with a student message.

This calls Claude Code for real, on the signed-in Claude Code account, so it uses plan usage.
The automated tests never do; this is for trying a conversation by hand after changing chat.md.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from degree_planner_backend.agent import chat_loop, loop
from degree_planner_backend.agent.chat_models import ChatRequest, ChatResponse
from degree_planner_backend.db import DB_PATH


def with_message(raw: Any, say: str) -> Any:
    """The request's JSON with say as the student's last message: it replaces a last student
    message and follows a last assistant message. Anything that is not a request is returned
    as it is, for ChatRequest to reject with its own message."""
    if not isinstance(raw, dict) or not isinstance(raw.get("messages"), list):
        return raw
    messages = list(raw["messages"])
    if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "student":
        messages = messages[:-1]
    return raw | {"messages": messages + [{"role": "student", "text": say}]}


def summarize(request: ChatRequest, response: ChatResponse, seconds: float) -> str:
    usage = response.usage
    lines = [
        f"student: {request.messages[-1].text}",
        f"steps: {usage.steps} of {chat_loop.CHAT_STEP_LIMIT}   tokens: {usage.input_tokens} in, "
        f"{usage.output_tokens} out   time: {seconds:.0f}s",
    ]
    if response.problems:
        lines.append("problems:")
        lines += [f"  - {problem}" for problem in response.problems]
    if response.changes:
        lines.append("changes:")
        for change in response.changes:
            where = f"{change.from_label or '-'} -> {change.to_label or '-'}"
            lines.append(f"  {change.kind} {change.code} {where}")
    else:
        lines.append("changes: none")
    if response.accepted_overrides:
        lines.append("accepted exceptions: " + ", ".join(o.code for o in response.accepted_overrides))
    else:
        lines.append("accepted exceptions: none")
    if response.still_open:
        lines.append("still open:")
        lines += [f"  - {message}" for message in response.still_open]
    if response.open_exceptions:
        lines.append("exceptions still to decide: " + ", ".join(response.open_exceptions))
    if response.proposed_plan is None:
        lines.append("proposed plan: none")
    else:
        plan = response.proposed_plan
        summary = plan.summary
        lines.append(
            f"proposed plan: {summary.total_credits:g} of {summary.total_credits_required:g} credits, "
            f"requirements met: {'yes' if summary.requirements_met else 'no'}"
        )
        for semester in plan.semesters:
            codes = ", ".join(course.code for course in semester.courses) or "(none)"
            lines.append(f"  {semester.label} ({semester.total_credits:g} cr): {codes}")
    lines += ["reply:", response.reply]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="try-chat", description="Run the chatbot on one chat request and print the result.")
    parser.add_argument("request", type=Path, help="a chat request JSON file (docs/chat-format.md)")
    parser.add_argument("--say", metavar="TEXT",
                        help="the student's message: replaces the file's last student message, or follows its last assistant one")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"catalog database (default: {DB_PATH.name})")
    parser.add_argument("--json", type=Path, metavar="FILE", help="also save the full response as JSON here")
    args = parser.parse_args(argv)

    try:
        text = args.request.read_text()
    except OSError as exc:
        print(f"cannot read {args.request}: {exc.strerror}", file=sys.stderr)
        return 2
    try:
        raw = json.loads(text)
        if args.say is not None:
            raw = with_message(raw, args.say)
        request = ChatRequest.model_validate(raw)
    except json.JSONDecodeError as exc:
        print(f"{args.request} is not a valid chat request:\nnot JSON: {exc}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"{args.request} is not a valid chat request:\n{exc}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"no database at {args.db}; load the data first (uv run load-data)", file=sys.stderr)
        return 2

    connection = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
    started = time.monotonic()
    try:
        response = chat_loop.run_chat(connection, request)
    except loop.ClaudeCodeError as exc:
        print(f"Claude Code could not run: {exc}. Is it installed and signed in (run `claude` once)?", file=sys.stderr)
        return 1
    finally:
        connection.close()

    print(summarize(request, response, time.monotonic() - started))
    if args.json:
        # by_alias: prerequisite edges are written as "from", not "from_" (BUG-031).
        args.json.write_text(response.model_dump_json(by_alias=True, indent=2))
        print(f"\nfull response saved to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
