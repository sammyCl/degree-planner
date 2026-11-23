"""Deterministic checks for the local example eval (plans/AGENT-PLAN.md, "Eval runner").

An example file (backend/eval/examples/*.json, documented in that folder's README.md) holds an agent
request and its "also must" checks. deterministic_verdict(connection, example, response) passes when
the agent loop returned status "ok" (the validator accepted the plan) and every check holds.
No model calls: this is plain code over the AgentResponse.

Examples are read strictly: an unknown check type, a missing or unknown field, or a semester name
that is not one of the request's labels is an error when the file is loaded, never a check that
quietly passes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse
from degree_planner_backend.lookups import get_program
from degree_planner_backend.models import Program
from degree_planner_backend.plan_models import Plan

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "eval" / "examples"


class _Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    why: str | None = None


class MaxSemesterCredits(_Check):
    type: Literal["max_semester_credits"]
    limit: float
    from_: str | None = Field(default=None, alias="from")
    through: str | None = None


class CourseInSemester(_Check):
    type: Literal["course_in_semester"]
    code: str
    semester: str


class NotPlanned(_Check):
    type: Literal["not_planned"]
    codes: list[str] = Field(min_length=1)


class CompletedNotPlanned(_Check):
    type: Literal["completed_not_planned"]


class PlannedCredits(_Check):
    type: Literal["planned_credits"]
    equals: float


class InEverySemester(_Check):
    type: Literal["in_every_semester"]
    code: str


class CountPlanned(_Check):
    type: Literal["count_planned"]
    codes: list[str] = Field(min_length=1)
    exactly: int = Field(ge=0)


class CreditsFrom(_Check):
    type: Literal["credits_from"]
    codes: list[str] = Field(min_length=1)
    through: str | None = None
    equals: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _one_bound(self) -> CreditsFrom:
        if (self.equals is None) == (self.max is None):
            raise ValueError("credits_from needs exactly one of equals or max")
        return self


class MinorUnsharedCredits(_Check):
    type: Literal["minor_unshared_credits"]
    minor: str
    major: str
    min: float


class FlowchartMatch(_Check):
    type: Literal["flowchart_match"]
    flowchart: dict[str, list[str]]
    tolerance: int = Field(ge=0)
    min_matched: int = Field(ge=1)


class ReviewRequired(_Check):
    type: Literal["review_required"]
    by: str


Check = Annotated[
    Union[
        MaxSemesterCredits, CourseInSemester, NotPlanned, CompletedNotPlanned, PlannedCredits, InEverySemester,
        CountPlanned, CreditsFrom, MinorUnsharedCredits, FlowchartMatch, ReviewRequired,
    ],
    Field(discriminator="type"),
]


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    name: str
    difficulty: Literal["simple", "medium", "hard"]
    request: AgentRequest
    also_must: list[Check]

    @model_validator(mode="after")
    def _labels_exist(self) -> Example:
        labels = self.request.semester_labels()
        for check in self.also_must:
            named = [getattr(check, name, None) for name in ("from_", "through", "semester")]
            if isinstance(check, FlowchartMatch):
                named += list(check.flowchart)
            for label in named:
                if label is not None and label not in labels:
                    raise ValueError(f"{check.type}: {label!r} is not one of the request's semesters {labels}")
        return self

    @property
    def needs_review(self) -> str | None:
        return next((c.by for c in self.also_must if isinstance(c, ReviewRequired)), None)


def load_example(path: Path) -> Example:
    return Example.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_examples(directory: Path = EXAMPLES_DIR) -> list[Example]:
    """Every example file in directory and its private/ folder, sorted by id."""
    paths = sorted(directory.glob("*.json")) + sorted((directory / "private").glob("*.json"))
    examples = [load_example(path) for path in paths]
    ids = [e.id for e in examples]
    if len(set(ids)) != len(ids):
        raise ValueError(f"two example files share an id: {sorted(ids)}")
    return sorted(examples, key=lambda e: e.id)


@dataclass(frozen=True)
class CheckResult:
    type: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DeterministicVerdict:
    passed: bool
    results: tuple[CheckResult, ...]

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if not r.passed)


def deterministic_verdict(connection: sqlite3.Connection, example: Example, response: AgentResponse) -> DeterministicVerdict:
    """Status "ok" plus every also_must check. A review_required check is not decided here."""
    results = [CheckResult(
        "validator_ok", response.status == "ok",
        "the validator accepted the plan" if response.status == "ok"
        else "status cannot_work: " + "; ".join(response.problems or ("no problems given",)),
    )]
    plan = response.plan
    for check in example.also_must:
        if isinstance(check, ReviewRequired):
            continue
        if plan is None:
            results.append(CheckResult(check.type, False, "no plan to check"))
            continue
        results.append(_run(connection, example, plan, check))
    return DeterministicVerdict(passed=all(r.passed for r in results), results=tuple(results))


# ---------------------------------------------------------------------------------- the checks

def _fmt(credits: float) -> str:
    return f"{credits:g}"


def _planned(plan: Plan) -> list[tuple[int, str, str, float]]:
    """(semester index, label, code, credits) for every planned course, in order."""
    return [
        (i, semester.label, course.code, course.credits)
        for i, semester in enumerate(plan.semesters)
        for course in semester.courses
        if course.status == "planned"
    ]


def _index(plan: Plan, label: str | None, default: int) -> int:
    if label is None:
        return default
    return next(i for i, s in enumerate(plan.semesters) if s.label == label)


def _run(connection: sqlite3.Connection, example: Example, plan: Plan, check: Check) -> CheckResult:
    planned = _planned(plan)
    codes_planned = [code for _, _, code, _ in planned]

    if isinstance(check, MaxSemesterCredits):
        first = _index(plan, check.from_, 0)
        last = _index(plan, check.through, len(plan.semesters) - 1)
        over = []
        for i in range(first, last + 1):
            credits = sum(c for j, _, _, c in planned if j == i)
            if credits > check.limit:
                over.append(f"{plan.semesters[i].label} has {_fmt(credits)}")
        span = f"{plan.semesters[first].label} to {plan.semesters[last].label}"
        return CheckResult(check.type, not over,
                           f"over {_fmt(check.limit)} credits: {', '.join(over)}" if over
                           else f"at most {_fmt(check.limit)} credits a semester, {span}")

    if isinstance(check, CourseInSemester):
        where = [label for _, label, code, _ in planned if code == check.code]
        ok = check.semester in where
        return CheckResult(check.type, ok, f"{check.code} in {check.semester}" if ok
                           else f"{check.code} is in {', '.join(where) or 'no semester'}, not {check.semester}")

    if isinstance(check, NotPlanned):
        found = sorted({c for c in codes_planned if c in check.codes})
        return CheckResult(check.type, not found, f"planned anyway: {', '.join(found)}" if found
                           else f"none of {', '.join(check.codes)} planned")

    if isinstance(check, CompletedNotPlanned):
        done = {c.code for c in example.request.student.completed_courses}
        again = sorted({c for c in codes_planned if c in done})
        return CheckResult(check.type, not again, f"planned again: {', '.join(again)}" if again
                           else f"none of the {len(done)} completed courses planned again")

    if isinstance(check, PlannedCredits):
        total = sum(c for _, _, _, c in planned)
        ok = abs(total - check.equals) < 0.001
        return CheckResult(check.type, ok, f"{_fmt(total)} planned credits" + ("" if ok else f", not {_fmt(check.equals)}"))

    if isinstance(check, InEverySemester):
        missing = [s.label for s in plan.semesters if check.code not in {c.code for c in s.courses}]
        return CheckResult(check.type, not missing, f"{check.code} missing from {', '.join(missing)}" if missing
                           else f"{check.code} in all {len(plan.semesters)} semesters")

    if isinstance(check, CountPlanned):
        found = sorted({c for c in codes_planned if c in check.codes})
        ok = len(found) == check.exactly
        return CheckResult(check.type, ok, f"{len(found)} planned ({', '.join(found) or 'none'}), "
                                           f"{'as required' if ok else f'need exactly {check.exactly}'}")

    if isinstance(check, CreditsFrom):
        last = _index(plan, check.through, len(plan.semesters) - 1)
        used = [(code, c) for i, _, code, c in planned if i <= last and code in check.codes]
        total = sum(c for _, c in used)
        if check.equals is not None:
            ok, want = abs(total - check.equals) < 0.001, f"need exactly {_fmt(check.equals)}"
        else:
            ok, want = total <= check.max + 0.001, f"at most {_fmt(check.max)}"
        until = f" through {plan.semesters[last].label}" if check.through else ""
        listed = ", ".join(code for code, _ in used) or "none"
        return CheckResult(check.type, ok, f"{_fmt(total)} credits from {listed}{until} ({want})")

    if isinstance(check, MinorUnsharedCredits):
        return _minor_unshared(connection, example, plan, check)

    if isinstance(check, FlowchartMatch):
        place = {}
        for i, _, code, _ in planned:
            place.setdefault(code, i)
        matched, off = 0, []
        for label, codes in check.flowchart.items():
            want = _index(plan, label, 0)
            for code in codes:
                got = place.get(code)
                if got is not None and abs(got - want) <= check.tolerance:
                    matched += 1
                else:
                    off.append(f"{code} ({'not planned' if got is None else plan.semesters[got].label}, "
                               f"flowchart {label})")
        total = sum(len(codes) for codes in check.flowchart.values())
        ok = matched >= check.min_matched
        detail = f"{matched} of {total} flowchart courses within {check.tolerance} semester(s) (need {check.min_matched})"
        return CheckResult(check.type, ok, detail + (f"; off: {', '.join(off)}" if off else ""))

    raise TypeError(f"no check for {check!r}")  # pragma: no cover - every Check type is handled above


def _minor_unshared(connection: sqlite3.Connection, example: Example, plan: Plan, check: MinorUnsharedCredits) -> CheckResult:
    """The minor rule: at least `min` of the minor's credits must not also fill a requirement of the
    major other than free electives (policy-minor-requirements, BUG-036).

    Taken in the student's favor, since the plan does not say which course fills which group:
    - A course is shared when the major needs it: it is in a major "all" group, or in a listed
      major choose group that the plan's other courses do not already fill. Major choose groups
      with no list are free electives and never make a course shared.
    - The minor is filled group by group from the plan and completed courses, unshared courses
      first, whole courses only, up to each group's credits; a minor group with no list takes any
      course that is not already counted for the minor.
    """
    year = example.request.student.catalog_year
    minor: Program = get_program(connection, check.minor, year)
    major: Program = get_program(connection, check.major, year)
    credits: dict[str, float] = {c.code: c.credits for c in example.request.student.completed_courses}
    for _, _, code, c in _planned(plan):
        credits.setdefault(code, c)
    have = set(credits)

    major_all = {code for g in major.requirement_groups if g.kind == "all" for code in g.courses or []}

    def shared(code: str) -> bool:
        if code in major_all:
            return True
        for g in major.requirement_groups:
            if g.kind == "choose_credits" and g.courses and code in g.courses:
                others = sum(credits[c] for c in g.courses if c in have and c != code and c not in major_all)
                if others < (g.credits_required or 0.0):
                    return True
        return False

    used: dict[str, bool] = {}  # code -> shared, for courses counted toward the minor
    for g in minor.requirement_groups:
        if g.kind == "all":
            for code in g.courses or []:
                if code in have:
                    used.setdefault(code, shared(code))
            continue
        pool = [c for c in (g.courses if g.courses else sorted(have)) if c in have and c not in used]
        pool.sort(key=shared)  # unshared first
        got = 0.0
        for code in pool:
            if got >= (g.credits_required or 0.0):
                break
            used[code] = shared(code)
            got += credits[code]

    unshared = sum(credits[c] for c, is_shared in used.items() if not is_shared)
    shared_codes = sorted(c for c, is_shared in used.items() if is_shared)
    ok = unshared >= check.min
    return CheckResult(check.type, ok,
                       f"{_fmt(unshared)} minor credits not shared with {check.major} (need {_fmt(check.min)}); "
                       f"shared: {', '.join(shared_codes) or 'none'}")
