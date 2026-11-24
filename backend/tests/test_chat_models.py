import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from degree_planner_backend.agent.chat_models import (
    CHANGES_MAX,
    MESSAGE_MAX,
    MESSAGES_MAX,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    PlanChange,
)
from degree_planner_backend.agent.request_models import PROBLEM_MAX, SEMESTERS_MAX_BACHELOR, SEMESTERS_MAX_GRADUATE

DOCS = Path(__file__).resolve().parents[2] / "docs"


def _plan() -> dict:
    return json.loads((DOCS / "plan-format.sample.json").read_text())


def _semester(n: int, label: str) -> dict:
    return {"semester_id": f"sem-{n}", "label": label, "courses": [], "total_credits": 0.0}


def _request(**changes) -> dict:
    request = {"plan": _plan(), "messages": [{"role": "student", "text": "Can CSCI400 move to fall?"}]}
    request.update(changes)
    return request


def _usage() -> dict:
    return {"input_tokens": 1200, "output_tokens": 300, "steps": 3}


def _move() -> dict:
    return {"kind": "move", "code": "CSCI400", "from_label": "Spring 2027", "to_label": "Fall 2027"}


def _response(**changes) -> dict:
    response = {"reply": "Here is the change.", "usage": _usage()}
    response.update(changes)
    return response


# --- samples ---------------------------------------------------------------


def test_sample_files_match_the_models():
    ChatRequest.model_validate_json((DOCS / "chat-request.sample.json").read_text())
    ChatResponse.model_validate_json((DOCS / "chat-response.sample.json").read_text())


def test_sample_response_change_matches_its_plans():
    """The sample's move is really what differs between the two sample plans."""
    request = json.loads((DOCS / "chat-request.sample.json").read_text())
    response = json.loads((DOCS / "chat-response.sample.json").read_text())

    def where(plan):
        return {c["code"]: s["label"] for s in plan["semesters"] for c in s["courses"]}

    before, after = where(request["plan"]), where(response["proposed_plan"])
    moved = {code: (before[code], after[code]) for code in before if before[code] != after.get(code)}
    assert moved == {"CSCI400": ("Spring 2027", "Fall 2027")}
    assert response["changes"] == [_move()]


# --- request ---------------------------------------------------------------


def test_request_minimal():
    request = ChatRequest.model_validate(_request())
    assert request.overrides == ()
    assert request.semester_labels() == ["Fall 2026", "Spring 2027"]


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(_request(start_term="Fall 2026"))


def test_request_needs_a_message():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(_request(messages=[]))


def test_request_message_limit():
    turns = [{"role": "student" if i % 2 == 0 else "assistant", "text": f"message {i}"} for i in range(MESSAGES_MAX + 1)]
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(_request(messages=turns))
    ChatRequest.model_validate(_request(messages=turns[1:]))  # 40, ending with the student


def test_request_last_message_must_be_the_students():
    messages = [{"role": "student", "text": "Hi"}, {"role": "assistant", "text": "Hello"}]
    with pytest.raises(ValidationError, match="student"):
        ChatRequest.model_validate(_request(messages=messages))


@pytest.mark.parametrize("text", ["", "   ", "​​", "\n\t"])
def test_message_needs_visible_text(text):
    with pytest.raises(ValidationError):
        ChatMessage(role="student", text=text)


def test_message_length_limit():
    ChatMessage(role="student", text="a" * MESSAGE_MAX)
    with pytest.raises(ValidationError):
        ChatMessage(role="student", text="a" * (MESSAGE_MAX + 1))


@pytest.mark.parametrize("role", ["user", "system", "Student", ""])
def test_message_role(role):
    with pytest.raises(ValidationError):
        ChatMessage(role=role, text="hi")


def test_request_needs_semesters():
    plan = _plan()
    plan["semesters"] = []
    with pytest.raises(ValidationError, match="no semesters"):
        ChatRequest.model_validate(_request(plan=plan))


@pytest.mark.parametrize("label", ["Fall2026", "fall 2026", "Winter 2026", "Fall ２０２６", "Fall 26", ""])
def test_request_rejects_bad_labels(label):
    plan = _plan()
    plan["semesters"][0]["label"] = label
    with pytest.raises(ValidationError, match="label"):
        ChatRequest.model_validate(_request(plan=plan))


def test_request_rejects_repeated_labels():
    plan = _plan()
    plan["semesters"][1]["label"] = "Fall 2026"
    with pytest.raises(ValidationError, match="once"):
        ChatRequest.model_validate(_request(plan=plan))


@pytest.mark.parametrize(("level", "limit"), [("bachelor", SEMESTERS_MAX_BACHELOR), ("master", SEMESTERS_MAX_GRADUATE)])
def test_request_semester_limit(level, limit):
    def plan_with(count):
        plan = _plan()
        plan["student"]["degree_level"] = level
        plan["semesters"] = [_semester(i, f"Fall {2026 + i}") for i in range(count)]
        return plan

    ChatRequest.model_validate(_request(plan=plan_with(limit)))
    with pytest.raises(ValidationError, match="at most"):
        ChatRequest.model_validate(_request(plan=plan_with(limit + 1)))


def test_request_overrides_cleaned_and_deduped():
    overrides = [{"type": "exception_claimed", "code": "csci 400"}, {"type": "exception_claimed", "code": "CSCI400"}]
    request = ChatRequest.model_validate(_request(overrides=overrides))
    assert [(o.type, o.code) for o in request.overrides] == [("exception_claimed", "CSCI400")]


def test_request_rejects_non_overridable_override():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(_request(overrides=[{"type": "broken_prerequisite", "code": "CSCI400"}]))


def test_request_is_frozen():
    request = ChatRequest.model_validate(_request())
    with pytest.raises(ValidationError):
        request.messages = ()


# --- plan change -----------------------------------------------------------


def test_change_kinds():
    PlanChange(**_move())
    PlanChange(kind="add", code="CSCI403", to_label="Fall 2027")
    PlanChange(kind="remove", code="CSCI370", from_label="Fall 2027")


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "add", "code": "CSCI403"},
        {"kind": "add", "code": "CSCI403", "from_label": "Fall 2026", "to_label": "Fall 2027"},
        {"kind": "remove", "code": "CSCI403"},
        {"kind": "remove", "code": "CSCI403", "from_label": "Fall 2026", "to_label": "Fall 2027"},
        {"kind": "move", "code": "CSCI403", "from_label": "Fall 2026"},
        {"kind": "move", "code": "CSCI403", "to_label": "Fall 2026"},
        {"kind": "move", "code": "CSCI403", "from_label": "Fall 2026", "to_label": "Fall 2026"},
        {"kind": "swap", "code": "CSCI403", "from_label": "Fall 2026", "to_label": "Fall 2027"},
    ],
)
def test_change_rejects_bad_shapes(change):
    with pytest.raises(ValidationError):
        PlanChange(**change)


def test_change_code_cleaned():
    assert PlanChange(kind="add", code="csci 403", to_label="Fall 2027").code == "CSCI403"


@pytest.mark.parametrize("code", ["", "CSCI", "403", "not a course"])
def test_change_rejects_bad_code(code):
    with pytest.raises(ValidationError):
        PlanChange(kind="add", code=code, to_label="Fall 2027")


# --- response --------------------------------------------------------------


def test_response_without_proposal():
    response = ChatResponse.model_validate(_response())
    assert response.proposed_plan is None and response.changes == () and response.accepted_overrides == ()


def test_response_with_move():
    ChatResponse.model_validate(_response(proposed_plan=_plan(), changes=[_move()], still_open=["CSCI400 needs MATH201."]))


def test_response_with_accepted_exception_only():
    overrides = [{"type": "exception_claimed", "code": "CSCI400"}]
    response = ChatResponse.model_validate(_response(proposed_plan=_plan(), accepted_overrides=overrides))
    assert response.changes == ()


@pytest.mark.parametrize("reply", ["", "  ", "​"])
def test_response_needs_reply(reply):
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(_response(reply=reply))


def test_response_changes_need_a_plan():
    with pytest.raises(ValidationError, match="proposed_plan"):
        ChatResponse.model_validate(_response(changes=[_move()]))
    with pytest.raises(ValidationError, match="proposed_plan"):
        ChatResponse.model_validate(_response(accepted_overrides=[{"type": "exception_claimed", "code": "CSCI400"}]))


def test_response_plan_needs_a_change():
    with pytest.raises(ValidationError, match="change something"):
        ChatResponse.model_validate(_response(proposed_plan=_plan()))


def test_response_still_open_needs_a_plan():
    with pytest.raises(ValidationError, match="still_open"):
        ChatResponse.model_validate(_response(still_open=["CSCI400 needs MATH201."]))


def test_response_stopped_run_has_no_plan():
    ChatResponse.model_validate(_response(problems=["The chatbot stopped after 12 steps without finishing."]))
    with pytest.raises(ValidationError, match="stopped early"):
        ChatResponse.model_validate(_response(proposed_plan=_plan(), changes=[_move()], problems=["Timed out."]))


def test_response_line_limits():
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(_response(problems=["a" * (PROBLEM_MAX + 1)]))
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(_response(problems=[" "]))


def test_response_change_limit():
    changes = [{"kind": "add", "code": "CSCI403", "to_label": "Fall 2027"}] * (CHANGES_MAX + 1)
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(_response(proposed_plan=_plan(), changes=changes))


def test_response_accepted_overrides_deduped_and_limited_to_exceptions():
    overrides = [{"type": "exception_claimed", "code": "csci400"}, {"type": "exception_claimed", "code": "CSCI400"}]
    response = ChatResponse.model_validate(_response(proposed_plan=_plan(), accepted_overrides=overrides))
    assert len(response.accepted_overrides) == 1
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(
            _response(proposed_plan=_plan(), accepted_overrides=[{"type": "requirement_unmet", "code": "CSCI400"}])
        )


def test_response_dumps_edges_with_from():
    """FastAPI dumps by alias; a saved response should too (BUG-031)."""
    response = ChatResponse.model_validate_json((DOCS / "chat-response.sample.json").read_text())
    dumped = json.loads(response.model_dump_json(by_alias=True))
    assert "from" in dumped["proposed_plan"]["prerequisite_edges"][0]
