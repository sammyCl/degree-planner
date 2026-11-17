"""Pydantic models for the plan format (docs/plan-format.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompletedCourse(BaseModel):
    code: str
    credits: float
    term: str
    transfer_from: str | None = None


class Student(BaseModel):
    degree_level: Literal["bachelor", "master", "phd", "combined", "minor", "asi"]
    programs: list[str]
    catalog_year: str
    completed_courses: list[CompletedCourse] = Field(default_factory=list)


class PlannedCourse(BaseModel):
    course_id: str
    code: str
    title: str
    credits: float
    status: Literal["planned", "completed"]


class Semester(BaseModel):
    semester_id: str
    label: str
    courses: list[PlannedCourse] = Field(default_factory=list)
    total_credits: float = 0.0


class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


FlagType = Literal[
    "broken_prerequisite",
    "credit_shortfall",
    "requirement_unmet",
    "double_count_exceeded",
    "exception_claimed",
]
FlagSeverity = Literal["error", "warning"]


class Flag(BaseModel):
    flag_id: str
    type: FlagType
    severity: FlagSeverity
    course_id: str | None
    message: str
    overridable: bool
    overridden: bool = False


class Summary(BaseModel):
    total_credits: float
    total_credits_required: float
    requirements_met: bool


class Plan(BaseModel):
    plan_id: str | None = None
    student: Student
    semesters: list[Semester]
    prerequisite_edges: list[Edge] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    summary: Summary
