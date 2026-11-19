import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from degree_planner_backend.agent.request_models import (
    SEMESTERS_MAX_BACHELOR,
    SEMESTERS_MAX_GRADUATE,
    AgentRequest,
    AgentResponse,
    semester_labels,
)
from degree_planner_backend.plan_models import Plan

DOCS = Path(__file__).resolve().parents[2] / "docs"


def _student() -> dict:
    return {
        "degree_level": "bachelor",
        "programs": ["csci-bs-general"],
        "catalog_year": "2026-2027",
        "completed_courses": [{"code": "MATH111", "credits": 4, "term": "aplcredit", "transfer_from": None}],
    }


def _plan(requirements_met: bool) -> Plan:
    sample = json.loads((DOCS / "plan-format.sample.json").read_text())
    sample["summary"]["requirements_met"] = requirements_met
    return Plan.model_validate(sample)


def _usage() -> dict:
    return {"input_tokens": 1200, "output_tokens": 300, "steps": 3}


def test_sample_files_match_the_models():
    AgentRequest.model_validate_json((DOCS / "agent-request.sample.json").read_text())
    AgentResponse.model_validate_json((DOCS / "agent-response.sample.json").read_text())


def test_request_minimal():
    request = AgentRequest.model_validate({"student": _student(), "semesters": 8, "start_term": "Fall 2026"})
    assert request.overrides == []
    assert request.semester_labels()[:3] == ["Fall 2026", "Spring 2027", "Fall 2027"]
    assert len(request.semester_labels()) == 8


@pytest.mark.parametrize(
    "start, count, expected",
    [
        ("Fall 2026", 3, ["Fall 2026", "Spring 2027", "Fall 2027"]),
        ("Spring 2027", 3, ["Spring 2027", "Fall 2027", "Spring 2028"]),
        ("Summer 2027", 3, ["Summer 2027", "Fall 2027", "Spring 2028"]),
        ("Fall 2026", 1, ["Fall 2026"]),
    ],
)
def test_semester_labels_without_summers(start, count, expected):
    assert semester_labels(start, count) == expected


@pytest.mark.parametrize(
    "start, count, expected",
    [
        ("Fall 2026", 4, ["Fall 2026", "Spring 2027", "Summer 2027", "Fall 2027"]),
        ("Spring 2027", 4, ["Spring 2027", "Summer 2027", "Fall 2027", "Spring 2028"]),
        ("Summer 2027", 4, ["Summer 2027", "Fall 2027", "Spring 2028", "Summer 2028"]),
    ],
)
def test_semester_labels_with_summers(start, count, expected):
    assert semester_labels(start, count, include_summers=True) == expected


def test_request_include_summers():
    base = {"student": _student(), "semesters": 3, "start_term": "Spring 2027"}
    assert AgentRequest.model_validate(base).include_summers is False
    request = AgentRequest.model_validate({**base, "include_summers": True})
    assert request.semester_labels() == ["Spring 2027", "Summer 2027", "Fall 2027"]


@pytest.mark.parametrize("term", ["fall 2026", "Fall26", "Winter 2026", "Fall 2026 ", "", "2026 Fall"])
def test_request_rejects_bad_start_term(term):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate({"student": _student(), "semesters": 8, "start_term": term})


def _request(level: str, count: int) -> dict:
    return {"student": {**_student(), "degree_level": level}, "semesters": count, "start_term": "Fall 2026"}


@pytest.mark.parametrize(
    "level, limit",
    [
        ("bachelor", SEMESTERS_MAX_BACHELOR),
        ("combined", SEMESTERS_MAX_BACHELOR),
        ("minor", SEMESTERS_MAX_BACHELOR),
        ("asi", SEMESTERS_MAX_BACHELOR),
        ("master", SEMESTERS_MAX_GRADUATE),
        ("phd", SEMESTERS_MAX_GRADUATE),
    ],
)
def test_semester_count_limit_by_level(level, limit):
    assert AgentRequest.model_validate(_request(level, 1)).semesters == 1
    assert AgentRequest.model_validate(_request(level, limit)).semesters == limit
    for bad in (0, -1, limit + 1):
        with pytest.raises(ValidationError):
            AgentRequest.model_validate(_request(level, bad))


def test_semester_limits_are_18_and_15():
    assert SEMESTERS_MAX_BACHELOR == 18
    assert SEMESTERS_MAX_GRADUATE == 15


def test_request_rejects_unknown_fields():
    # Free-text notes are deliberately not in the first version.
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(
            {"student": _student(), "semesters": 8, "start_term": "Fall 2026", "notes": "no Fridays"}
        )


def test_override_types_must_be_flag_types():
    base = {"student": _student(), "semesters": 8, "start_term": "Fall 2026"}
    ok = AgentRequest.model_validate({**base, "overrides": [{"type": "exception_claimed", "code": "MNGN501"}]})
    assert ok.overrides[0].code == "MNGN501"
    plan_wide = AgentRequest.model_validate({**base, "overrides": [{"type": "requirement_unmet"}]})
    assert plan_wide.overrides[0].code is None
    with pytest.raises(ValidationError):
        AgentRequest.model_validate({**base, "overrides": [{"type": "not_a_flag", "code": "MNGN501"}]})


def test_response_ok():
    response = AgentResponse(status="ok", plan=_plan(True), explanation="Eight semesters.", usage=_usage())
    assert response.problems == []


def test_response_ok_needs_a_passing_plan():
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=None, explanation="x", usage=_usage())
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=_plan(False), explanation="x", usage=_usage())
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=_plan(True), explanation="x", problems=["y"], usage=_usage())


def test_response_cannot_work_keeps_best_attempt():
    response = AgentResponse(
        status="cannot_work",
        plan=_plan(False),
        explanation="CSCI400 cannot fit after its prerequisite in 8 semesters.",
        problems=["CSCI400 needs CSCI262 first"],
        usage=_usage(),
    )
    assert response.plan is not None
    no_attempt = AgentResponse(
        status="cannot_work", plan=None, explanation="x", problems=["program not loaded"], usage=_usage()
    )
    assert no_attempt.plan is None


def test_response_cannot_work_needs_a_problem():
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=_plan(False), explanation="x", usage=_usage())


def test_usage_rejects_negative_counts():
    with pytest.raises(ValidationError):
        AgentResponse(
            status="cannot_work",
            plan=None,
            explanation="x",
            problems=["y"],
            usage={"input_tokens": -1, "output_tokens": 0, "steps": 0},
        )
