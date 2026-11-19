"""What the backend sends the agent and what the agent returns (docs/agent-request-format.md).

The student and the plan reuse the plan format (plan_models.py), so there is one definition of each.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from degree_planner_backend.agent.tools import (
    _COURSE_CODE,
    OVERRIDABLE_FLAG_TYPES,
    SEMESTERS_MAX,
    _clean_stored_code,
)
from degree_planner_backend.plan_models import FlagType, Plan, Student

# ASCII digits only: \d would also match other scripts' digits ("Fall ２０２６").
_TERM = re.compile(r"^(Fall|Spring|Summer) ([0-9]{4})$")
START_YEAR_MIN = 2000
START_YEAR_MAX = 2500

OVERRIDES_MAX = 50
OVERRIDE_CODE_MAX = 20

# Most semesters a student can ask for, by degree level. Combined BS+MS, minors and ASIs go with a
# bachelor's, so they share its limit; master's and PhD are graduate.
SEMESTERS_MAX_BACHELOR = SEMESTERS_MAX  # 18, shared with check_plan in tools.py
SEMESTERS_MAX_GRADUATE = 15
_GRADUATE_LEVELS = {"master", "phd"}


def semesters_max(degree_level: str) -> int:
    return SEMESTERS_MAX_GRADUATE if degree_level in _GRADUATE_LEVELS else SEMESTERS_MAX_BACHELOR


class Override(BaseModel):
    """A flag the student chose to override in the frontend, keyed by course code (not course id)
    so it survives the agent moving the course.

    Only overridable flag types are accepted (OVERRIDABLE_FLAG_TYPES in tools.py). Those are all
    about one course, so code is required; it is cleaned up like the tools do ('mngn 501' -> 'MNGN501')."""

    model_config = ConfigDict(extra="forbid")

    type: FlagType
    code: str = Field(max_length=OVERRIDE_CODE_MAX)

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in OVERRIDABLE_FLAG_TYPES:
            allowed = ", ".join(sorted(OVERRIDABLE_FLAG_TYPES))
            raise ValueError(f"{value!r} flags cannot be overridden; only {allowed} can")
        return value

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        code = _clean_stored_code(value)
        if not _COURSE_CODE.fullmatch(code):
            raise ValueError(f"{value!r} is not a course code like MNGN501")
        return code


class AgentRequest(BaseModel):
    """What the backend sends the agent loop."""

    model_config = ConfigDict(extra="forbid")

    student: Student
    # Strict: true, 8.0 or "8" is a frontend bug, so it is rejected instead of converted.
    semesters: StrictInt = Field(ge=1)
    start_term: str
    include_summers: StrictBool = False
    overrides: list[Override] = Field(default_factory=list, max_length=OVERRIDES_MAX)

    @field_validator("start_term")
    @classmethod
    def _check_start_term(cls, value: str) -> str:
        match = _TERM.fullmatch(value)
        if not match:
            raise ValueError('start_term must look like "Fall 2026", "Spring 2027" or "Summer 2027"')
        if not START_YEAR_MIN <= int(match.group(2)) <= START_YEAR_MAX:
            raise ValueError(f"start_term year must be from {START_YEAR_MIN} to {START_YEAR_MAX}")
        return value

    @field_validator("overrides")
    @classmethod
    def _drop_duplicate_overrides(cls, value: list[Override]) -> list[Override]:
        # Checked after each code is cleaned, so 'mngn 501' and 'MNGN501' count as the same.
        seen: set[tuple[str, str]] = set()
        unique = []
        for override in value:
            key = (override.type, override.code)
            if key not in seen:
                seen.add(key)
                unique.append(override)
        return unique

    @model_validator(mode="after")
    def _check_semester_count(self) -> AgentRequest:
        limit = semesters_max(self.student.degree_level)
        if self.semesters > limit:
            raise ValueError(f"semesters must be at most {limit} for degree level {self.student.degree_level!r}")
        return self

    def semester_labels(self) -> list[str]:
        """The labels the agent plans into, made by code so the model never invents a term."""
        return semester_labels(self.start_term, self.semesters, self.include_summers)


def semester_labels(start_term: str, count: int, include_summers: bool = False) -> list[str]:
    """Each semester counts toward count, summers included when include_summers is true.
    A Summer start term is always kept, even when later summers are not."""
    match = _TERM.fullmatch(start_term)
    if match is None:
        raise ValueError(f"bad start term {start_term!r}")
    season, year = match.group(1), int(match.group(2))
    labels = []
    for _ in range(count):
        labels.append(f"{season} {year}")
        if season == "Fall":
            season, year = "Spring", year + 1
        elif season == "Spring" and include_summers:
            season = "Summer"
        else:  # Spring without summers, or Summer: next is Fall of the same year
            season = "Fall"
    return labels


class Usage(BaseModel):
    """Token counts for one request, summed over every model call in the loop (for the eval and cost)."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    steps: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_steps(self) -> Usage:
        if self.steps == 0 and (self.input_tokens or self.output_tokens):
            raise ValueError("tokens were used, so steps must be at least 1")
        return self


class AgentResponse(BaseModel):
    """What the agent loop returns.

    status "ok": plan is present and the validator says requirements_met.
    status "cannot_work": problems says why; plan is the last attempt with the validator's flags,
    or None if the agent never proposed one.
    The plan is always rebuilt and checked by the backend, never taken from the model as is.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "cannot_work"]
    plan: Plan | None
    explanation: str
    problems: list[str] = Field(default_factory=list)
    usage: Usage

    @field_validator("explanation")
    @classmethod
    def _check_explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation must not be empty")
        return value

    @field_validator("problems")
    @classmethod
    def _check_problems(cls, value: list[str]) -> list[str]:
        if any(not problem.strip() for problem in value):
            raise ValueError("each problem must say something")
        return value

    @model_validator(mode="after")
    def _check_status(self) -> AgentResponse:
        if self.status == "ok":
            if self.plan is None:
                raise ValueError('status "ok" needs a plan')
            if not self.plan.summary.requirements_met:
                raise ValueError('status "ok" needs a plan whose summary has requirements_met true')
            # The summary could disagree with the flags in a hand-built or edited plan. An override
            # only counts on a flag the student may override (BUG-032: the validator trusts any).
            open_errors = [
                f.flag_id
                for f in self.plan.flags
                if f.severity == "error" and not (f.overridden and f.overridable)
            ]
            if open_errors:
                raise ValueError(f'status "ok" needs a plan with no open error flags; found {", ".join(open_errors)}')
            if self.problems:
                raise ValueError('status "ok" must not list problems')
        elif not self.problems:
            raise ValueError('status "cannot_work" needs at least one problem')
        return self
