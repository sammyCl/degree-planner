"""Build the checker canaries: one good Example 1 plan and copies that each break one thing.

    uv run python eval/canaries/build_canaries.py        (from backend/; needs the loaded database)

Each canary is an AgentResponse JSON, checked by the backend the same way the agent loop checks a
plan (loop._build_response), and written next to this file. Judge one with only the checker:

    uv run eval-examples --checker-only eval/canaries/ex1-missing-required.json --example 1

The checker should say does_not_work, with a cited Mines page, for every broken canary. If it says
works for one, it cannot be trusted to judge the agent's plans. The good plan is the control: the
validator accepts it, so a checker finding there is either something our data misses or a checker
mistake, worth reading either way.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.eval_checks import load_examples
from degree_planner_backend.agent.mcp_server import context_for
from degree_planner_backend.agent.request_models import Usage
from degree_planner_backend.db import DB_PATH

HERE = Path(__file__).resolve().parent

# The CS General Track flowchart (data/Undergraduate Programs/Computer Science/Computer Science.pdf,
# p. 2) with its placeholders filled: CSCI370 in Senior Fall (no summers), and the focus-area
# courses split into 5 CS electives and 3 free electives (CONFLICT-LOG.md #17). 128 credits.
GOOD = {
    "Fall 2026": ["MATH111", "HASS100", "CHGN121", "CSM101", "CSCI128"],
    "Spring 2027": ["MATH112", "PHGN100", "PAGN202", "EDNS151", "CSCI200"],
    "Fall 2027": ["MATH213", "CSM202", "PHGN200", "CSCI358", "CSCI210"],
    "Spring 2028": ["MATH225", "HASS215", "EBGN201", "CSCI220", "MATH201"],
    "Fall 2028": ["MATH332", "MATH334", "CSCI306", "CSCI403", "CSCI446"],
    "Spring 2029": ["EBGN321", "HASS200", "ENGY200", "CSCI341", "CSCI406", "CSCI432"],
    "Fall 2029": ["HASS202", "CSCI400", "CSCI370", "CSCI445", "EDNS200"],
    "Spring 2030": ["HASS400", "CSCI442", "LIFL113", "CSCI410", "CSCI475", "MNGN210"],
}


def broken(name: str) -> dict[str, list[str]]:
    plan = {label: list(codes) for label, codes in GOOD.items()}
    if name == "missing-required":
        # CSCI442 Operating Systems is required; a free elective takes its place, so credits still add up.
        plan["Spring 2030"][plan["Spring 2030"].index("CSCI442")] = "LIFL115"
    elif name == "prereq-order":
        # CSCI210 needs CSCI200: swap them, so CSCI210 comes a semester before its prerequisite.
        plan["Spring 2027"][plan["Spring 2027"].index("CSCI200")] = "CSCI210"
        plan["Fall 2027"][plan["Fall 2027"].index("CSCI210")] = "CSCI200"
    elif name == "too-few-credits":
        # Three free electives (9 credits) dropped: 119 of 128.
        for label, code in (("Spring 2029", "ENGY200"), ("Fall 2029", "EDNS200"), ("Spring 2030", "MNGN210")):
            plan[label].remove(code)
    else:
        raise ValueError(name)
    return plan


CANARIES = {
    "good": GOOD,
    "missing-required": broken("missing-required"),
    "prereq-order": broken("prereq-order"),
    "too-few-credits": broken("too-few-credits"),
}


def build(connection: sqlite3.Connection, semesters: dict[str, list[str]]):
    example = next(e for e in load_examples() if e.id == 1)
    assert list(semesters) == example.request.semester_labels()
    plan_input = {"semesters": [{"label": label, "courses": codes} for label, codes in semesters.items()]}
    return loop._build_response(
        connection, context_for(example.request), plan_input, "Canary plan, written by hand.", None,
        Usage(input_tokens=0, output_tokens=0, steps=0),
    )


def main() -> int:
    if not DB_PATH.exists():
        print(f"no database at {DB_PATH}; load the data first (uv run load-data ../data)", file=sys.stderr)
        return 2
    connection = sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
    try:
        for name, semesters in CANARIES.items():
            response = build(connection, semesters)
            path = HERE / f"ex1-{name}.json"
            path.write_text(json.dumps(json.loads(response.model_dump_json(by_alias=True)), indent=2) + "\n")
            summary = response.plan.summary if response.plan else None
            credits = f"{summary.total_credits:g} of {summary.total_credits_required:g} credits" if summary else "no plan"
            print(f"{path.name}: {response.status}, {credits}")
            for problem in response.problems:
                print(f"    {problem}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
