"""Pydantic models for the plan format (docs/plan-format.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from degree_planner_backend.models import Requirement


class CompletedCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    # BUG-029: negative credits would reach the validator's credit totals; ge=0 (not gt=0) because
    # a 0-credit completed course is real (e.g. EENG500 Graduate Seminar).
    credits: float = Field(ge=0, allow_inf_nan=False)
    term: str
    transfer_from: str | None = None
    # Both optional and only for showing the record (the validator ignores them): the course's title as the
    # transcript wrote it (useful for placeholder credit like "FREE1XX-3", "Free Elective: Art History"), and
    # whether the transcript lists it as in progress (counted as completed so it is not planned again).
    title: str | None = None
    in_progress: bool = False


class Student(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree_level: Literal["bachelor", "master", "phd", "combined", "minor", "asi", "certificate"]
    # BUG-028: a student always has at least one program; an empty list only used to fail later,
    # inside build_plan.
    programs: list[str] = Field(min_length=1)
    catalog_year: str
    completed_courses: list[CompletedCourse] = Field(default_factory=list)


class PlannedCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    code: str
    title: str
    credits: float
    status: Literal["planned", "completed"]
    # Denormalized from the catalog, same reason as title: the frontend's About panel can show a
    # course's description and corequisites without a second lookup. Optional/defaulted so an
    # older plan (or one built before a course was found in the catalog) still validates.
    description: str = ""
    corequisites: Requirement | None = None


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
    "semester_overload",
    "stale_program_year",
    "assumed_equivalent",
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


class RequirementStatus(BaseModel):
    """Whether one requirement group of one program is met, for the planner page's checklist (computed by check_plan)."""

    model_config = ConfigDict(extra="forbid")

    program_id: str
    group_id: str
    label: str
    kind: Literal["all", "choose_credits", "requirement"]
    met: bool
    # choose_credits (and the nominal count of a requirement group): what the group needs and what the plan earns
    credits_required: float | None = None
    credits_earned: float | None = None
    # an "all" group: how many of its fixed courses the plan lacks
    missing_count: int = 0


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
    # Every requirement group of every program the student is in, in the programs' own order, with whether the plan meets
    # it. The same checks that raise requirement_unmet and credit_shortfall flags, reported for the groups that pass too,
    # so the planner page can show a checklist (Core, Free electives, ...). Never trusted from the client.
    requirement_status: list[RequirementStatus] = Field(default_factory=list)
