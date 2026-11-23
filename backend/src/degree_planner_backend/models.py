"""Pydantic models for the common data format (docs/data-format.md)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class CourseRequirement(BaseModel):
    type: Literal["course"]
    code: str
    min_grade: str | None = None


class ExceptionRequirement(BaseModel):
    type: Literal["exception"]
    label: str


class AndRequirement(BaseModel):
    type: Literal["AND"]
    of: list[Requirement]


class OrRequirement(BaseModel):
    type: Literal["OR"]
    of: list[Requirement]


Requirement = Annotated[
    Union[CourseRequirement, ExceptionRequirement, AndRequirement, OrRequirement],
    Field(discriminator="type"),
]

AndRequirement.model_rebuild()
OrRequirement.model_rebuild()


class Source(BaseModel):
    url: str
    page: int | None = None


class Course(BaseModel):
    code: str
    subject: str
    number: str
    title: str
    credits: float
    credits_min: float | None = None
    credits_max: float | None = None
    # Courses the catalog calls equivalent ("Equivalent with ..."), in both directions (BUG-041):
    # one satisfies a prerequisite on the other, and only one of them counts toward a degree.
    equivalent_with: list[str] = Field(default_factory=list)
    description: str
    prerequisites: Requirement | None = None
    corequisites: Requirement | None = None
    catalog_year: str
    source: Source | None = None


class RequirementGroup(BaseModel):
    group_id: str
    label: str
    kind: Literal["all", "choose_credits"]
    courses: list[str] | None = None
    credits_required: float | None = None

    @model_validator(mode="after")
    def _check_credits_required(self) -> RequirementGroup:
        if self.kind == "choose_credits" and self.credits_required is None:
            raise ValueError("credits_required is required when kind is 'choose_credits'")
        return self


class DoubleCount(BaseModel):
    program_id: str
    shared_courses: list[str]
    shared_credit_limit: float


class Program(BaseModel):
    program_id: str
    name: str
    degree_level: Literal["bachelor", "master", "phd", "combined", "minor", "asi"]
    catalog_year: str
    total_credits_required: float
    requirement_groups: list[RequirementGroup]
    combines: list[str] = Field(default_factory=list)
    double_counts_with: list[DoubleCount] = Field(default_factory=list)


class Form(BaseModel):
    form_id: str
    name: str
    applies_to: list[str]
    max_credits: float | None = None
    requires: str | None = None
    url: str | None = None
    notes: str | None = None


class DataFile(BaseModel):
    """The shape of one collected-data JSON file: any subset of courses/programs/forms."""

    courses: list[Course] = Field(default_factory=list)
    programs: list[Program] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
