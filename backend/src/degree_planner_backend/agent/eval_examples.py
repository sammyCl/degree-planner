"""Run the five examples through the real agent and judge each plan (local testing only).

    uv run eval-examples                    # every example, once
    uv run eval-examples --example 1        # one example (repeat --example for several)
    uv run eval-examples --runs 3           # each example three times, for pass counts
    uv run eval-examples --no-checker       # deterministic checks only (cheaper while iterating)
    uv run eval-examples --checker-only RESPONSE.json --example 1   # judge a saved response (canaries)
    uv run eval-examples --tally eval/results/2026-11-22T15-04-05  # recount, with reviews recorded

A run passes when the validator accepted the plan (status "ok"), every "also must" check in the
example holds (eval_checks.py), and the adversarial checker (checker.py) finds no blocking problem
on the Mines websites. An example with review_required (Example 5) then waits for a person: write
<run file stem>.review.json next to the run, {"verdict": "pass" or "fail", "notes": "..."}, and
run --tally on the folder.

Every run is saved to backend/eval/results/<timestamp>/ (gitignored), with the full response, the
check results, the checker's findings and the token counts, for EVAL.md later. This calls Claude
Code for real, on the signed-in account, so it uses plan usage: the planner once per run and the
checker once per run.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from degree_planner_backend.agent import checker, loop
from degree_planner_backend.agent.eval_checks import (
    EXAMPLES_DIR,
    DeterministicVerdict,
    Example,
    deterministic_verdict,
    load_examples,
)
from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse
from degree_planner_backend.db import DB_PATH

RESULTS_DIR = EXAMPLES_DIR.parent / "results"

AgentFn = Callable[[sqlite3.Connection, AgentRequest], AgentResponse]
CheckerFn = Callable[[sqlite3.Connection, Example, AgentResponse], checker.CheckerVerdict]

# Outcomes of one run. Only "pass" counts as passed.
PASS, FAIL, CHECKER_ERROR, AWAITING_REVIEW, NOT_CHECKED = (
    "pass", "fail", "checker error", "awaiting review", "deterministic only")


def outcome(det: DeterministicVerdict, verdict: checker.CheckerVerdict | None, needs_review: str | None,
            review: dict[str, Any] | None = None) -> str:
    if not det.passed:
        return FAIL  # a broken plan fails whatever the checker says
    if verdict is None:
        return NOT_CHECKED
    if verdict.status == "error":
        return CHECKER_ERROR
    if verdict.status == "does_not_work":
        return FAIL
    if needs_review:
        if review is None:
            return AWAITING_REVIEW
        return PASS if review.get("verdict") == "pass" else FAIL
    return PASS


def run_one(connection: sqlite3.Connection, example: Example, run_number: int, *, agent: AgentFn,
            check: CheckerFn | None, response: AgentResponse | None = None) -> dict[str, Any]:
    """One run: the agent (unless a saved response is given), the checks, then the checker."""
    started = time.monotonic()
    if response is None:
        response = agent(connection, example.request)
    agent_seconds = time.monotonic() - started
    det = deterministic_verdict(connection, example, response)
    verdict = None
    checker_seconds = 0.0
    if check is not None and response.plan is not None:
        started = time.monotonic()
        verdict = check(connection, example, response)
        checker_seconds = time.monotonic() - started
    return {
        "example": example.id,
        "name": example.name,
        "run": run_number,
        "outcome": outcome(det, verdict, example.needs_review),
        "needs_review": example.needs_review,
        "deterministic": {"passed": det.passed, "results": [asdict(r) for r in det.results]},
        "checker": None if verdict is None else {
            "status": verdict.status,
            "error": verdict.error,
            "summary": verdict.summary,
            "findings": [f.model_dump() for f in verdict.findings],
            "pages_read": list(verdict.pages_read),
            "verified": None if verdict.verified is None else verdict.verified.model_dump(),
            "usage": verdict.usage.model_dump(),
            "seconds": round(checker_seconds, 1),
        },
        "agent": {"usage": response.usage.model_dump(), "seconds": round(agent_seconds, 1)},
        # by_alias: prerequisite edges are written as "from", not "from_" (BUG-031).
        "response": json.loads(response.model_dump_json(by_alias=True)),
    }


def describe(record: dict[str, Any]) -> str:
    """One line per run, then the reasons for anything that did not pass."""
    det = record["deterministic"]
    verdict = record["checker"]
    agent = record["agent"]
    usage = agent["usage"]
    parts = [
        f"Example {record['example']} run {record['run']}: {record['outcome'].upper()}",
        f"checks {'pass' if det['passed'] else 'FAIL'}",
        f"checker {verdict['status'] if verdict else 'skipped'}",
        f"agent {usage['steps']} steps, {usage['input_tokens']} in / {usage['output_tokens']} out, {agent['seconds']:.0f}s",
    ]
    if verdict:
        cu = verdict["usage"]
        parts.append(f"checker {cu['steps']} steps, {cu['input_tokens']} in / {cu['output_tokens']} out, "
                     f"{verdict['seconds']:.0f}s")
    lines = ["   ".join(parts)]
    lines += [f"    check {r['type']}: {r['detail']}" for r in det["results"] if not r["passed"]]
    if verdict:
        if verdict["error"]:
            lines.append(f"    checker error: {verdict['error']}")
        for f in verdict["findings"]:
            cite = f" ({f['url']})" if f["url"] else ""
            lines.append(f"    checker {f['severity']}: {f['claim']}{cite}")
    if record["outcome"] == AWAITING_REVIEW:
        lines.append(f"    waiting for {record['needs_review']}'s review: write {record['file_stem']}.review.json, "
                     "then run --tally on this folder")
    return "\n".join(lines)


def tally(records: list[dict[str, Any]]) -> str:
    total = len(records)
    passed = sum(1 for r in records if r["outcome"] == PASS)
    lines = [f"Passed: {passed} of {total} runs"]
    for example_id in sorted({r["example"] for r in records}):
        mine = [r for r in records if r["example"] == example_id]
        counts = {o: sum(1 for r in mine if r["outcome"] == o) for o in (PASS, FAIL, CHECKER_ERROR, AWAITING_REVIEW, NOT_CHECKED)}
        rest = ", ".join(f"{n} {o}" for o, n in counts.items() if n and o != PASS)
        lines.append(f"  Example {example_id}: {counts[PASS]} of {len(mine)} passed" + (f" ({rest})" if rest else ""))
    agent_in = sum(r["agent"]["usage"]["input_tokens"] for r in records)
    agent_out = sum(r["agent"]["usage"]["output_tokens"] for r in records)
    checker_in = sum(r["checker"]["usage"]["input_tokens"] for r in records if r["checker"])
    checker_out = sum(r["checker"]["usage"]["output_tokens"] for r in records if r["checker"])
    lines.append(f"Tokens: agent {agent_in} in / {agent_out} out; checker {checker_in} in / {checker_out} out")
    return "\n".join(lines)


def save(folder: Path, record: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record['file_stem']}.json").write_text(json.dumps(record, indent=2))


def retally(folder: Path) -> list[dict[str, Any]]:
    """Re-read a results folder, applying any review files, and update the saved outcomes."""
    records = []
    for path in sorted(folder.glob("ex*-run*.json")):
        if path.name.endswith(".review.json"):
            continue
        record = json.loads(path.read_text())
        review_path = path.with_name(path.stem + ".review.json")
        if record.get("needs_review") and record["outcome"] in (AWAITING_REVIEW, PASS, FAIL) and review_path.exists():
            review = json.loads(review_path.read_text())
            if review.get("verdict") not in ("pass", "fail"):
                raise ValueError(f"{review_path}: verdict must be \"pass\" or \"fail\"")
            checks_ok = record["deterministic"]["passed"] and record["checker"] and record["checker"]["status"] == "works"
            record["outcome"] = (PASS if review["verdict"] == "pass" else FAIL) if checks_ok else FAIL
            record["review"] = review
            path.write_text(json.dumps(record, indent=2))
        records.append(record)
    return records


def main(argv: list[str] | None = None, *, agent: AgentFn = loop.run_agent, check: CheckerFn = checker.run_checker,
         out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="eval-examples", description="Run the examples and judge each plan.")
    parser.add_argument("--example", type=int, action="append", metavar="ID", help="only this example (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="runs per example (default 1)")
    parser.add_argument("--no-checker", action="store_true", help="skip the adversarial checker")
    parser.add_argument("--checker-only", type=Path, metavar="RESPONSE.json",
                        help="judge a saved agent response instead of running the agent (needs one --example)")
    parser.add_argument("--tally", type=Path, metavar="RESULTS_DIR", help="recount a results folder, with reviews")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"catalog database (default: {DB_PATH.name})")
    parser.add_argument("--examples-dir", type=Path, default=EXAMPLES_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.tally:
        if not args.tally.is_dir():
            out(f"no results folder at {args.tally}")
            return 2
        records = retally(args.tally)
        for record in records:
            out(describe(record))
        out(tally(records))
        return 0
    if args.runs < 1:
        out("--runs must be at least 1")
        return 2
    if args.checker_only and len(args.example or []) != 1:
        out("--checker-only needs exactly one --example")
        return 2
    if not args.db.exists():
        out(f"no database at {args.db}; load the data first (uv run load-data ../data)")
        return 2

    examples = load_examples(args.examples_dir)
    if args.example:
        missing = sorted(set(args.example) - {e.id for e in examples})
        if missing:
            out(f"no example with id {', '.join(map(str, missing))} (have {', '.join(str(e.id) for e in examples)})")
            return 2
        examples = [e for e in examples if e.id in args.example]

    folder = args.results_dir / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    connection = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
    records = []
    try:
        for example in examples:
            for run_number in range(1, (1 if args.checker_only else args.runs) + 1):
                saved = AgentResponse.model_validate_json(args.checker_only.read_text()) if args.checker_only else None
                try:
                    record = run_one(connection, example, run_number, agent=agent,
                                     check=None if args.no_checker else check, response=saved)
                except loop.ClaudeCodeError as exc:
                    out(f"Claude Code could not run: {exc}. Is it installed and signed in (run `claude` once)?")
                    return 1
                record["file_stem"] = f"ex{example.id}-run{run_number}" + ("-checker-only" if saved else "")
                save(folder, record)
                records.append(record)
                out(describe(record))
    finally:
        connection.close()
    out(tally(records))
    out(f"Results saved to {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
