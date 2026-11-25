import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from degree_planner_backend.agent.request_models import (
    EXPLANATION_MAX,
    PROBLEM_MAX,
    PROBLEMS_MAX,
    OVERRIDES_MAX,
    SEMESTERS_MAX_BACHELOR,
    SEMESTERS_MAX_GRADUATE,
    AgentRequest,
    AgentResponse,
    semester_labels,
)
from degree_planner_backend.agent.tools import FLAG_MESSAGE_MAX, FLAGS_SHOWN_MAX
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
    """The plan-format sample. A passing plan has no flags; a failing one keeps the sample's
    broken CSCI400 prerequisite."""
    sample = json.loads((DOCS / "plan-format.sample.json").read_text())
    sample["summary"]["requirements_met"] = requirements_met
    if requirements_met:
        sample["flags"] = []
        sample["summary"]["total_credits"] = sample["summary"]["total_credits_required"]
    return Plan.model_validate(sample)


def _usage() -> dict:
    return {"input_tokens": 1200, "output_tokens": 300, "steps": 3}


def test_sample_files_match_the_models():
    AgentRequest.model_validate_json((DOCS / "agent-request.sample.json").read_text())
    AgentResponse.model_validate_json((DOCS / "agent-response.sample.json").read_text())


def test_request_minimal():
    request = AgentRequest.model_validate({"student": _student(), "semesters": 8, "start_term": "Fall 2026"})
    assert request.overrides == ()
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
        ("certificate", SEMESTERS_MAX_BACHELOR),
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


def _with_overrides(overrides: list) -> dict:
    return {"student": _student(), "semesters": 8, "start_term": "Fall 2026", "overrides": overrides}


def test_override_accepted_and_code_cleaned():
    request = AgentRequest.model_validate(_with_overrides([{"type": "exception_claimed", "code": " mngn 501 "}]))
    assert request.overrides[0].code == "MNGN501"


@pytest.mark.parametrize(
    "flag_type",
    ["broken_prerequisite", "credit_shortfall", "requirement_unmet", "double_count_exceeded", "not_a_flag"],
)
def test_override_rejects_flag_types_that_cannot_be_overridden(flag_type):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(_with_overrides([{"type": flag_type, "code": "CSCI400"}]))


@pytest.mark.parametrize("code", ["", "   ", "not a course!!", "A" * 10000, "MNGN501; DROP", "МNGN501"])
def test_override_rejects_bad_codes(code):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(_with_overrides([{"type": "exception_claimed", "code": code}]))


def test_override_needs_a_code():
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(_with_overrides([{"type": "exception_claimed"}]))
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(_with_overrides([{"type": "exception_claimed", "code": None}]))


def test_override_duplicates_are_dropped():
    request = AgentRequest.model_validate(
        _with_overrides(
            [
                {"type": "exception_claimed", "code": "MNGN501"},
                {"type": "exception_claimed", "code": "mngn 501"},
                {"type": "exception_claimed", "code": "CSCI400"},
            ]
        )
    )
    assert [o.code for o in request.overrides] == ["MNGN501", "CSCI400"]


def test_override_list_is_capped():
    many = [{"type": "exception_claimed", "code": f"CSCI{i:03d}"} for i in range(OVERRIDES_MAX + 1)]
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(_with_overrides(many))
    assert len(AgentRequest.model_validate(_with_overrides(many[:OVERRIDES_MAX])).overrides) == OVERRIDES_MAX


@pytest.mark.parametrize("term", ["Fall ２０２６", "Fall ٢٠٢٦"])
def test_request_rejects_non_ascii_digits_in_start_term(term):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate({"student": _student(), "semesters": 8, "start_term": term})


@pytest.mark.parametrize(
    "term, ok",
    [
        ("Fall 1999", False),
        ("Fall 0001", False),
        ("Spring 2000", True),
        ("Fall 2026", True),
        ("Summer 2500", True),
        ("Fall 2501", False),
        ("Fall 9999", False),
    ],
)
def test_request_start_year_is_2000_to_2500(term, ok):
    body = {"student": _student(), "semesters": 8, "start_term": term}
    if ok:
        AgentRequest.model_validate(body)
    else:
        with pytest.raises(ValidationError):
            AgentRequest.model_validate(body)


@pytest.mark.parametrize("value", [True, False, 8.0, "8"])
def test_request_semesters_must_be_a_real_integer(value):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate({"student": _student(), "semesters": value, "start_term": "Fall 2026"})


@pytest.mark.parametrize("value", ["yes", "false", 1, 0])
def test_request_include_summers_must_be_a_real_boolean(value):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(
            {"student": _student(), "semesters": 8, "start_term": "Fall 2026", "include_summers": value}
        )


def test_request_strict_types_still_parse_from_json():
    raw = json.dumps({"student": _student(), "semesters": 8, "start_term": "Fall 2026", "include_summers": True})
    request = AgentRequest.model_validate_json(raw)
    assert request.semesters == 8 and request.include_summers is True
    with pytest.raises(ValidationError):
        AgentRequest.model_validate_json(raw.replace('"semesters": 8', '"semesters": "8"'))


def test_response_ok():
    response = AgentResponse(status="ok", plan=_plan(True), explanation="Eight semesters.", usage=_usage())
    assert response.problems == ()


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


def test_response_ok_rejects_open_error_flags():
    # requirements_met says true, but the sample's broken prerequisite flag is still open.
    plan = _plan(False)
    summary = plan.summary.model_copy(update={"requirements_met": True, "total_credits": plan.summary.total_credits_required})
    plan = plan.model_copy(update={"summary": summary})
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=plan, explanation="x", usage=_usage())
    # The sample's broken prerequisite cannot be overridden, so marking it overridden does not help.
    forged = plan.model_copy(update={"flags": [f.model_copy(update={"overridden": True}) for f in plan.flags]})
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=forged, explanation="x", usage=_usage())
    # Marking it overridable by hand does not help either: the type decides, not the flag's field.
    relabeled = plan.model_copy(
        update={"flags": [f.model_copy(update={"overridden": True, "overridable": True}) for f in plan.flags]}
    )
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=relabeled, explanation="x", usage=_usage())
    # An error of a type the student may override, and did override, counts as handled.
    allowed = plan.model_copy(
        update={
            "flags": [
                f.model_copy(update={"type": "exception_claimed", "overridden": True, "overridable": True})
                for f in plan.flags
            ]
        }
    )
    assert AgentResponse(status="ok", plan=allowed, explanation="x", usage=_usage()).status == "ok"


def test_bachelor_limit_is_shared_with_check_plan():
    from degree_planner_backend.agent.tools import SEMESTERS_MAX

    assert SEMESTERS_MAX_BACHELOR == SEMESTERS_MAX == 18


@pytest.mark.parametrize("explanation", ["", "   ", "\n"])
def test_response_rejects_empty_explanation(explanation):
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=None, explanation=explanation, problems=["y"], usage=_usage())


@pytest.mark.parametrize("problems", [[""], ["  "], ["real reason", ""]])
def test_response_rejects_empty_problems(problems):
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=None, explanation="x", problems=problems, usage=_usage())


def test_usage_steps_must_match_tokens():
    with pytest.raises(ValidationError):
        AgentResponse(
            status="cannot_work",
            plan=None,
            explanation="x",
            problems=["y"],
            usage={"input_tokens": 500, "output_tokens": 50, "steps": 0},
        )
    # No model call at all (for example, a program that is not loaded) is fine.
    none_used = AgentResponse(
        status="cannot_work",
        plan=None,
        explanation="x",
        problems=["program not loaded"],
        usage={"input_tokens": 0, "output_tokens": 0, "steps": 0},
    )
    assert none_used.usage.steps == 0


def test_usage_rejects_negative_counts():
    with pytest.raises(ValidationError):
        AgentResponse(
            status="cannot_work",
            plan=None,
            explanation="x",
            problems=["y"],
            usage={"input_tokens": -1, "output_tokens": 0, "steps": 0},
        )


def test_ok_rejects_a_summary_short_on_credits():
    plan = _plan(True)
    short = plan.model_copy(update={"summary": plan.summary.model_copy(update={"total_credits": 14})})
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=short, explanation="x", usage=_usage())


def test_ok_allows_an_open_exception_warning():
    # Team decision 2026-11-19: the planner page shows the warning and the student overrides it there.
    plan = _plan(True)
    warning = {
        "flag_id": "f1",
        "type": "exception_claimed",
        "severity": "warning",
        "course_id": None,
        "message": "needs instructor approval",
        "overridable": True,
        "overridden": False,
    }
    with_warning = Plan.model_validate({**plan.model_dump(by_alias=True), "flags": [warning]})
    assert AgentResponse(status="ok", plan=with_warning, explanation="x", usage=_usage()).status == "ok"


def test_request_is_read_only_after_validation():
    request = AgentRequest.model_validate(
        {**_with_overrides([{"type": "exception_claimed", "code": "MNGN501"}])}
    )
    with pytest.raises(ValidationError):
        request.semesters = 500
    with pytest.raises(ValidationError):
        request.start_term = "Fall 2027"
    with pytest.raises(AttributeError):
        request.overrides.append("anything")
    with pytest.raises(ValidationError):
        request.overrides[0].type = "broken_prerequisite"


def test_response_is_read_only_after_validation():
    response = AgentResponse(status="cannot_work", plan=None, explanation="x", problems=["y"], usage=_usage())
    with pytest.raises(ValidationError):
        response.status = "ok"
    with pytest.raises(AttributeError):
        response.problems.append("z")
    with pytest.raises(ValidationError):
        response.usage.steps = 0


@pytest.mark.parametrize("text", ["\u200b\u200b", "\u200f", " \u00a0\t", "\u2028", "\ufeff"])
def test_invisible_text_does_not_count(text):
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=None, explanation=text, problems=["y"], usage=_usage())
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=None, explanation="x", problems=[text], usage=_usage())


def test_text_with_some_visible_characters_counts():
    response = AgentResponse(
        status="cannot_work", plan=None, explanation="\u200bCSCI400 needs CSCI262", problems=["\u00e9"], usage=_usage()
    )
    assert response.status == "cannot_work"


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "steps"])
@pytest.mark.parametrize("value", [True, "500", 5.0])
def test_usage_counts_are_strict(field, value):
    usage = {"input_tokens": 1, "output_tokens": 1, "steps": 1, field: value}
    with pytest.raises(ValidationError):
        AgentResponse(status="cannot_work", plan=None, explanation="x", problems=["y"], usage=usage)


def test_response_text_limits():
    def response(explanation="x", problems=("y",)):
        return AgentResponse(
            status="cannot_work", plan=None, explanation=explanation, problems=list(problems), usage=_usage()
        )

    assert (PROBLEMS_MAX, PROBLEM_MAX) == (FLAGS_SHOWN_MAX, FLAG_MESSAGE_MAX) == (30, 600)
    response(explanation="x" * EXPLANATION_MAX, problems=["p" * PROBLEM_MAX] * PROBLEMS_MAX)
    with pytest.raises(ValidationError):
        response(explanation="x" * (EXPLANATION_MAX + 1))
    with pytest.raises(ValidationError):
        response(problems=["p"] * (PROBLEMS_MAX + 1))
    with pytest.raises(ValidationError):
        response(problems=["p" * (PROBLEM_MAX + 1)])


# --- choices and checks (submit_summary) ---------------------------------------------------------


def test_choices_and_checks_default_to_empty() -> None:
    # Older responses (and the docs sample) have neither field, and still load.
    response = AgentResponse(status="ok", plan=_plan(True), explanation="Eight semesters.", usage=_usage())
    assert response.choices == () and response.checks == ()
    AgentResponse.model_validate_json((DOCS / "agent-response.sample.json").read_text())


def test_choices_and_checks_are_kept() -> None:
    response = AgentResponse(
        status="ok", plan=_plan(True), explanation="x", usage=_usage(),
        choices=["CSCI403 fills the elective."], checks=["Confirm CSCI403 is offered in the fall."],
    )
    assert response.choices == ("CSCI403 fills the elective.",)
    assert json.loads(response.model_dump_json())["checks"] == ["Confirm CSCI403 is offered in the fall."]


@pytest.mark.parametrize(
    "field, value",
    [
        ("choices", ["  "]),
        ("checks", ["​"]),
        ("choices", ["x" * 501]),
        ("checks", ["a"] * 13),
    ],
)
def test_bad_choices_or_checks_are_rejected(field: str, value: list[str]) -> None:
    with pytest.raises(ValidationError):
        AgentResponse(status="ok", plan=_plan(True), explanation="x", usage=_usage(), **{field: value})
