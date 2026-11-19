"""What the backend sends the agent and what the agent returns (docs/agent-request-format.md).

The student and the plan reuse the plan format (plan_models.py), so there is one definition of each.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from degree_planner_backend.plan_models import FlagType, Plan, Student

_TERM = re.compile(r"^(Fall|Spring|Summer) (\d{4})$")

# Most semesters a student can ask for, by degree level. Combined BS+MS, minors and ASIs go with a
# bachelor's, so they share its limit; master's and PhD are graduate.
SEMESTERS_MAX_BACHELOR = 18
SEMESTERS_MAX_GRADUATE = 15
_GRADUATE_LEVELS = {"master", "phd"}


def semesters_max(degree_level: str) -> int:
    return SEMESTERS_MAX_GRADUATE if degree_level in _GRADUATE_LEVELS else SEMESTERS_MAX_BACHELOR


class Override(BaseModel):
    """A flag the student chose to override in the frontend, keyed by course code (not course id)
    so it survives the agent moving the course. code is None for a plan-wide flag."""

    model_config = ConfigDict(extra="forbid")

    type: FlagType
    code: str | None = None


class AgentRequest(BaseModel):
    """What the backend sends the agent loop."""

    model_config = ConfigDict(extra="forbid")

    student: Student
    semesters: int = Field(ge=1)
    start_term: str
    include_summers: bool = False
    overrides: list[Override] = Field(default_factory=list)

    @field_validator("start_term")
    @classmethod
    def _check_start_term(cls, value: str) -> str:
        if not _TERM.fullmatch(value):
            raise ValueError('start_term must look like "Fall 2026", "Spring 2027" or "Summer 2027"')
        return value

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

    @model_validator(mode="after")
    def _check_status(self) -> AgentResponse:
        if self.status == "ok":
            if self.plan is None:
                raise ValueError('status "ok" needs a plan')
            if not self.plan.summary.requirements_met:
                raise ValueError('status "ok" needs a plan whose summary has requirements_met true')
            if self.problems:
                raise ValueError('status "ok" must not list problems')
        elif not self.problems:
            raise ValueError('status "cannot_work" needs at least one problem')
        return self
