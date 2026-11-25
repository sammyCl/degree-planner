"""Pydantic models for the plan format (docs/plan-format.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompletedCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    # BUG-029: negative credits would reach the validator's credit totals; ge=0 (not gt=0) because
    # a 0-credit completed course is real (e.g. EENG500 Graduate Seminar).
    credits: float = Field(ge=0, allow_inf_nan=False)
    term: str
    transfer_from: str | None = None


class Student(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree_level: Literal["bachelor", "master", "phd", "combined", "minor", "asi"]
    # BUG-028 (held back): agent/tools.py's check_plan has its own test for an empty programs list
    # (no_programs error), built by constructing Student(programs=[]) directly; rejecting that at
    # the model means that test can no longer build its scenario. Needs reconciling with that path
    # before this can reject here instead.
    programs: list[str]
    catalog_year: str
    completed_courses: list[CompletedCourse] = Field(default_factory=list)


class PlannedCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    code: str
    title: str
    credits: float
    status: Literal["planned", "completed"]


class Semester(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semester_id: str
    label: str
    courses: list[PlannedCourse] = Field(default_factory=list)
    total_credits: float = 0.0


class Edge(BaseModel):
    # BUG-031: serialize_by_alias=True so model_dump_json() writes "from" by default, the same as
    # FastAPI's response encoding; code that dumped without by_alias=True used to get "from_".
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="forbid")

    from_: str = Field(alias="from")
    to: str


FlagType = Literal[
    "broken_prerequisite",
    "credit_shortfall",
    "requirement_unmet",
    "double_count_exceeded",
    "exception_claimed",
    "ineligible_course",
]
FlagSeverity = Literal["error", "warning"]


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_id: str
    type: FlagType
    severity: FlagSeverity
    course_id: str | None
    message: str
    overridable: bool
    overridden: bool = False


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_credits: float
    total_credits_required: float
    requirements_met: bool


class CountsToward(BaseModel):
    """One requirement group a planned course counts toward (computed by check_plan, never trusted from the client)."""

    model_config = ConfigDict(extra="forbid")

    program_id: str
    group_id: str
    label: str


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    student: Student
    semesters: list[Semester]
    prerequisite_edges: list[Edge] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    summary: Summary
    # course_id -> the requirement groups that course fills, so the planner page can label a course "Core", "Free
    # elective", "Minor", and so on. Filled in by check_plan from the same assignment it uses for the group checks
    # (a course fills at most one group per program). A planned course missing from the map fills no group.
    counts_toward: dict[str, list[CountsToward]] = Field(default_factory=dict)
