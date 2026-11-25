"""Pydantic models for the common data format (docs/data-format.md)."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# BUG-019: a default catalog year for forms that don't carry their own.
_CATALOG_YEAR = r"^[0-9]{4}-[0-9]{4}$"
# BUG-014: an exception label is cleaned once here so every consumer (validator, frontend, agent)
# sees the same text, instead of each layer cleaning it again its own way. Matches
# agent/tools.py's clean_text exactly (format characters dropped, control characters become a
# space, whitespace runs collapse, "..." if still over the limit) so the two layers never disagree.
_LABEL_MAX = 200


def _clean_label(value: str) -> str:
    kept = []
    for char in value:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        kept.append(" " if category == "Cc" else char)
    cleaned = " ".join("".join(kept).split())
    if len(cleaned) <= _LABEL_MAX:
        return cleaned
    cut = _LABEL_MAX - 3
    while cut > 0 and unicodedata.combining(cleaned[cut]):
        cut -= 1
    return cleaned[:cut] + "..."


class CourseRequirement(BaseModel):
    type: Literal["course"]
    code: str
    min_grade: str | None = None


class ExceptionRequirement(BaseModel):
    type: Literal["exception"]
    # BUG-014: cleaned and truncated, not rejected for length — real scraped prerequisite text can
    # run past 200 characters (e.g. CEEN590's corequisite); emptied-out (all invisible characters)
    # is still rejected, since an exception with no real label is malformed data.
    label: str = Field(min_length=1, max_length=_LABEL_MAX)

    @field_validator("label", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _clean_label(value) if isinstance(value, str) else value


class AndRequirement(BaseModel):
    type: Literal["AND"]
    # BUG-010: an AND or OR of nothing is malformed data (an empty OR can never be true, an empty
    # AND is trivially true, and the data author almost certainly meant neither).
    of: list[Requirement] = Field(min_length=1)


class OrRequirement(BaseModel):
    type: Literal["OR"]
    of: list[Requirement] = Field(min_length=1)


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
    # BUG-023(a): a catalog year is always a "2026-2027"-shaped range, never free text.
    catalog_year: str = Field(pattern=_CATALOG_YEAR)
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
    # BUG-022: 0, negative, NaN or infinite credits_required would make a group impossible to fail
    # or let any amount of credits satisfy it.
    # Also used for a "requirement" group's nominal credit count (bookkeeping only, e.g. for a
    # printed total to add up); the validator decides whether the group is met from `requirement`
    # alone, never from this number.
    credits_required: float | None = Field(default=None, gt=0, allow_inf_nan=False)
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
        # BUG-026(c): an "all" group with no courses listed is malformed data, not a requirement
        # that is trivially met; a group with nothing to require shouldn't exist at all.
        if self.kind == "all" and not self.courses:
            raise ValueError("courses must be non-empty when kind is 'all'")
        return self


class DoubleCount(BaseModel):
    program_id: str
    shared_courses: list[str]
    shared_credit_limit: float = Field(gt=0, allow_inf_nan=False)


class Program(BaseModel):
    program_id: str
    name: str
    degree_level: Literal["bachelor", "master", "phd", "combined", "minor", "asi"]
    catalog_year: str = Field(pattern=_CATALOG_YEAR)
    total_credits_required: float = Field(gt=0, allow_inf_nan=False)
    requirement_groups: list[RequirementGroup]
    combines: list[str] = Field(default_factory=list)
    double_counts_with: list[DoubleCount] = Field(default_factory=list)
    # Only meaningful for degree_level "master"/"phd" (BUG-044): a combined-program undergraduate
    # may take 700-level credits only if the master's/PhD part is thesis-based. None means unknown,
    # so the validator does not flag it rather than guess.
    thesis_based: bool | None = None
    # BUG-021: rules the data format has no field for (e.g. "not open to QBE majors",
    # "CSCI423 and EBGN528 cannot both count"), as plain text for the agent to show the student;
    # never enforced by the validator, since it can't check free text.
    notes: list[str] = Field(default_factory=list)


class Form(BaseModel):
    form_id: str
    name: str
    # BUG-017: min_length=1 so a form applies to at least something; entries are normalized below.
    applies_to: list[str] = Field(min_length=1)
    max_credits: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    requires: str | None = None
    url: str | None = None
    notes: str | None = None
    # BUG-019: which catalog year this form/policy was taken from (the data loader fills this in
    # from the file's own catalog_year when an entry doesn't set one itself). Optional, not
    # required, so a form built without one (e.g. an existing test fixture) still loads; None just
    # means "year not known."
    catalog_year: str | None = Field(default=None, pattern=_CATALOG_YEAR)

    @field_validator("form_id", mode="before")
    @classmethod
    def _normalize_form_id(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("applies_to", mode="before")
    @classmethod
    def _normalize_applies_to(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.strip().lower() if isinstance(item, str) else item for item in value]
        return value

    @field_validator("url", mode="before")
    @classmethod
    def _only_https(cls, value: object) -> object:
        # BUG-017: a non-https url (or plain text that isn't a url at all) becomes None rather
        # than rejecting the whole form — url is already optional, so this is the same shape as a
        # form that never had one, not data loss the way dropping the form would be. agent/tools.py
        # does a stricter check on top (the real Mines domain, not just the scheme); this is only
        # the cheap, load-time half.
        if isinstance(value, str) and not value.lower().startswith("https://"):
            return None
        return value


class DataFile(BaseModel):
    """The shape of one collected-data JSON file: any subset of courses/programs/forms."""

    # BUG-019: a default catalog year for every form in this file that doesn't name its own; not a
    # field of DataFile's own data, just read by the loader before each Form is validated.
    catalog_year: str | None = None
    courses: list[Course] = Field(default_factory=list)
    programs: list[Program] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
