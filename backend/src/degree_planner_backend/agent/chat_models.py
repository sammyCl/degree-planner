"""What the frontend sends the chatbot and what the chatbot returns (docs/chat-format.md).

The backend keeps no chat state: every request carries the plan on the board, the overrides the
student already chose, and the conversation so far. The chatbot proposes; the student applies.
The plan, the overrides and the usage reuse the plan format and the agent request format, so
there is one definition of each.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from degree_planner_backend.agent.request_models import (
    _TERM,
    EXPLANATION_MAX,
    OVERRIDES_MAX,
    PROBLEM_MAX,
    PROBLEMS_MAX,
    Override,
    Usage,
    _has_visible_text,
    semesters_max,
)
from degree_planner_backend.agent.tools import _COURSE_CODE, _clean_stored_code
from degree_planner_backend.plan_models import Plan

# One message, either way. The chatbot's reply has the same limit as the planner's explanation.
MESSAGE_MAX = EXPLANATION_MAX  # 4000
# Messages one request may carry; the frontend drops the oldest past this.
MESSAGES_MAX = 40
# Plan changes one reply may propose: a student asks for one or two at a time.
CHANGES_MAX = 30


class ChatMessage(BaseModel):
    """One message in the conversation. Student text is untrusted: it goes into the prompt as
    the student's words, never as instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["student", "assistant"]
    text: str = Field(max_length=MESSAGE_MAX)

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        if not _has_visible_text(value):
            raise ValueError("a message must say something")
        return value


class ChatRequest(BaseModel):
    """What the frontend sends with each chat message.

    plan is the board as it is now (after any drag and drop); its semester labels are the ones
    the chatbot may use. The backend rebuilds and validates it, so its flags and summary are
    not trusted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: Plan
    overrides: tuple[Override, ...] = Field(default=(), max_length=OVERRIDES_MAX)
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=MESSAGES_MAX)

    @field_validator("overrides")
    @classmethod
    def _drop_duplicate_overrides(cls, value: tuple[Override, ...]) -> tuple[Override, ...]:
        return _unique_overrides(value)

    @field_validator("messages")
    @classmethod
    def _check_last_message(cls, value: tuple[ChatMessage, ...]) -> tuple[ChatMessage, ...]:
        if value and value[-1].role != "student":
            raise ValueError("the last message must be the student's")
        return value

    @model_validator(mode="after")
    def _check_semesters(self) -> ChatRequest:
        labels = [semester.label for semester in self.plan.semesters]
        if not labels:
            raise ValueError("the plan has no semesters")
        limit = semesters_max(self.plan.student.degree_level)
        if len(labels) > limit:
            raise ValueError(
                f"the plan has {len(labels)} semesters; at most {limit} for degree level "
                f"{self.plan.student.degree_level!r}"
            )
        for label in labels:
            if not _TERM.fullmatch(label):
                raise ValueError(f'semester label {label!r} must look like "Fall 2026"')
        if len(set(labels)) != len(labels):
            raise ValueError("each semester label must appear once")
        return self

    def semester_labels(self) -> list[str]:
        return [semester.label for semester in self.plan.semesters]


class PlanChange(BaseModel):
    """One change between the request's plan and the proposed plan, worked out by the backend
    by comparing the two, never written by the model.

    add: to_label only. remove: from_label only. move: both, different. Replacing one course with
    another shows as a remove and an add."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["add", "remove", "move"]
    code: str
    from_label: str | None = None
    to_label: str | None = None

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        code = _clean_stored_code(value)
        if not _COURSE_CODE.fullmatch(code):
            raise ValueError(f"{value!r} is not a course code like CSCI101")
        return code

    @model_validator(mode="after")
    def _check_labels(self) -> PlanChange:
        has_from, has_to = self.from_label is not None, self.to_label is not None
        if self.kind == "add" and (has_from or not has_to):
            raise ValueError("an add has a to_label and no from_label")
        if self.kind == "remove" and (has_to or not has_from):
            raise ValueError("a remove has a from_label and no to_label")
        if self.kind == "move":
            if not (has_from and has_to):
                raise ValueError("a move has both a from_label and a to_label")
            if self.from_label == self.to_label:
                raise ValueError("a move must go to a different semester")
        return self


class ChatResponse(BaseModel):
    """What the chatbot returns.

    reply: the chatbot's message to the student, always present.
    proposed_plan: the plan with the proposed changes and accepted exceptions, rebuilt and
        validated by the backend; None when nothing is proposed (a question, a clarifying
        question back, or a run that stopped). The student applies it; nothing is saved.
    changes, accepted_overrides: what the proposal changes; both empty exactly when there is no
        proposed_plan.
    still_open: error flags still open in the proposed plan, so a change that breaks something is
        shown rather than hidden. A proposal does not have to pass the validator: the student may
        want the change anyway.
    problems: why the run stopped early (step limit, timeout, error); then there is no proposal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: str = Field(max_length=MESSAGE_MAX)
    proposed_plan: Plan | None = None
    changes: tuple[PlanChange, ...] = Field(default=(), max_length=CHANGES_MAX)
    accepted_overrides: tuple[Override, ...] = Field(default=(), max_length=OVERRIDES_MAX)
    still_open: tuple[str, ...] = Field(default=(), max_length=PROBLEMS_MAX)
    problems: tuple[str, ...] = Field(default=(), max_length=PROBLEMS_MAX)
    usage: Usage

    @field_validator("reply")
    @classmethod
    def _check_reply(cls, value: str) -> str:
        if not _has_visible_text(value):
            raise ValueError("reply must not be empty")
        return value

    @field_validator("accepted_overrides")
    @classmethod
    def _drop_duplicate_overrides(cls, value: tuple[Override, ...]) -> tuple[Override, ...]:
        return _unique_overrides(value)

    @field_validator("still_open", "problems")
    @classmethod
    def _check_lines(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for line in value:
            if not _has_visible_text(line):
                raise ValueError("each line must say something")
            if len(line) > PROBLEM_MAX:
                raise ValueError(f"each line must be at most {PROBLEM_MAX} characters")
        return value

    @model_validator(mode="after")
    def _check_proposal(self) -> ChatResponse:
        proposes = bool(self.changes or self.accepted_overrides)
        if self.proposed_plan is None:
            if proposes:
                raise ValueError("changes or accepted_overrides need a proposed_plan")
            if self.still_open:
                raise ValueError("still_open needs a proposed_plan")
        else:
            if not proposes:
                raise ValueError("a proposed_plan must change something or accept an exception")
            if self.problems:
                raise ValueError("a run that stopped early must not propose a plan")
        return self


def _unique_overrides(value: tuple[Override, ...]) -> tuple[Override, ...]:
    """Keeps the first of each (type, code); codes are already cleaned, so 'mngn 501' and
    'MNGN501' count as the same."""
    seen: set[tuple[str, str]] = set()
    unique = []
    for override in value:
        key = (override.type, override.code)
        if key not in seen:
            seen.add(key)
            unique.append(override)
    return tuple(unique)
