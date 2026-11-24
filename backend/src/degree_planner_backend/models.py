"""Pydantic models for the common data format (docs/data-format.md)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# BUG-019: a default catalog year for forms that don't carry their own.
_CATALOG_YEAR = r"^[0-9]{4}-[0-9]{4}$"


class CourseRequirement(BaseModel):
    type: Literal["course"]
    code: str
    min_grade: str | None = None


class ExceptionRequirement(BaseModel):
    type: Literal["exception"]
    # BUG-014 (held back): agent/tools.py already cleans a label (drops invisible characters,
    # joins lines, cuts at 200 characters) at its own layer with its own exact rules; cleaning it
    # again here as well double-processes it and can disagree with the tool's own cut. Leave this
    # to Samantha to fold into the data format once the two layers are reconciled.
    label: str


class AndRequirement(BaseModel):
    type: Literal["AND"]
    # BUG-010 (held back): rejecting an empty "of" here means an already-loaded empty group (which
    # agent/tools.py's summarize_requirement already renders as "(empty OR group)") can no longer
    # be constructed directly either, which several of its tests rely on. Needs the same
    # reconciliation as BUG-014 before this can enforce min_length=1.
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
    # BUG-007: NaN/infinity loads as a value that then fails every later read of the catalog.
    credits: float = Field(allow_inf_nan=False)
    credits_min: float | None = Field(default=None, allow_inf_nan=False)
    credits_max: float | None = Field(default=None, allow_inf_nan=False)
    # Courses the catalog calls equivalent ("Equivalent with ..."), in both directions (BUG-041):
    # one satisfies a prerequisite on the other, and only one of them counts toward a degree.
    equivalent_with: list[str] = Field(default_factory=list)
    description: str
    prerequisites: Requirement | None = None
    corequisites: Requirement | None = None
    catalog_year: str
    source: Source | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: object) -> object:
        # BUG-011: store one form (uppercase, no spaces) so a lookup by the same rule always finds
        # it. The stricter shape check (3-4 letters, 3 digits, up to 2 trailing letters) is held
        # back: it would also reject the 14 known placeholder codes already in courses.json
        # (BUG-012, not this fix's data to touch) and needs coordinating with that cleanup first.
        return value.strip().upper().replace(" ", "") if isinstance(value, str) else value


class RequirementGroup(BaseModel):
    group_id: str
    label: str
    # "requirement" (BUG-038): the group's real rule is a logical AND/OR of courses, not a flat
    # list or a credit count (e.g. the Thorson first-year-core swap: HASS100+EDNS151, or
    # HNRS105+HNRS115, never a mix of the two pairs). Its `requirement` field decides whether the
    # group is met; `courses` may still list every course it mentions, for display and catalog
    # checks only.
    kind: Literal["all", "choose_credits", "requirement"]
    courses: list[str] | None = None
    # BUG-022 (held back): several of agent/tools.py's existing adversarial tests deliberately
    # store a program with credits_required/total_credits_required missing, zero or negative and
    # expect it to load with a data_warning, not be rejected by the loader. Needs Samantha to fold
    # this into that handling before it can reject at load.
    # Also used for a "requirement" group's nominal credit count (bookkeeping only, e.g. for a
    # printed total to add up); the validator decides whether the group is met from `requirement`
    # alone, never from this number.
    credits_required: float | None = None
    # Only meaningful for an "all" group (BUG-042): its courses must be planned in every fall and
    # spring semester of the plan, not just once anywhere (e.g. a 0-credit graduate seminar).
    every_semester: bool = False
    # Only for kind "requirement".
    requirement: Requirement | None = None

    @model_validator(mode="after")
    def _check_credits_required(self) -> RequirementGroup:
        if self.kind in ("choose_credits", "requirement") and self.credits_required is None:
            raise ValueError(f"credits_required is required when kind is {self.kind!r}")
        if self.kind == "requirement" and self.requirement is None:
            raise ValueError("requirement is required when kind is 'requirement'")
        # BUG-026(c) (held back): rejecting an "all" group with no courses here means it can no
        # longer load at all, but agent/tools.py already handles this leniently today — it loads
        # the program and adds a "kind 'all' with no courses" data_warning, which
        # test_program_all_group_without_courses_is_flagged depends on. Same call as the other
        # held-back bugs (see bugs.txt): reject at load, or keep tolerating it at the tool layer.
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
    # BUG-023(a) (held back): same reconciliation as BUG-022, applies to catalog_year too (an
    # existing test stores a program with an invalid catalog_year string on purpose).
    total_credits_required: float
    requirement_groups: list[RequirementGroup]
    combines: list[str] = Field(default_factory=list)
    double_counts_with: list[DoubleCount] = Field(default_factory=list)
    # Only meaningful for degree_level "master"/"phd" (BUG-044): a combined-program undergraduate
    # may take 700-level credits only if the master's/PhD part is thesis-based. None means unknown,
    # so the validator does not flag it rather than guess.
    thesis_based: bool | None = None


class Form(BaseModel):
    # BUG-017 (held back in full): agent/tools.py already normalizes form_id/applies_to, caps
    # max_credits, and allows only https URLs at its own layer, with tests built against forms the
    # loader stores as-is and the tool then cleans. Doing the same checks here too collapses
    # distinct raw ids/text the tool's own de-duplication and cleaning tests depend on seeing.
    form_id: str
    name: str
    applies_to: list[str]
    max_credits: float | None = None
    requires: str | None = None
    url: str | None = None
    notes: str | None = None
    # BUG-019: which catalog year this form/policy was taken from (the data loader fills this in
    # from the file's own catalog_year when an entry doesn't set one itself). Optional, not
    # required, so a form built without one (e.g. an existing test fixture) still loads; None just
    # means "year not known."
    catalog_year: str | None = Field(default=None, pattern=_CATALOG_YEAR)


class DataFile(BaseModel):
    """The shape of one collected-data JSON file: any subset of courses/programs/forms."""

    # BUG-019: a default catalog year for every form in this file that doesn't name its own; not a
    # field of DataFile's own data, just read by the loader before each Form is validated.
    catalog_year: str | None = None
    courses: list[Course] = Field(default_factory=list)
    programs: list[Program] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
