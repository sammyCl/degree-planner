"""Tests for the agent loop (agent/loop.py) with a scripted fake client: no API calls, no cost."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from degree_planner_backend.agent import loop
from degree_planner_backend.agent.loop import (
    CUT_OFF_PROBLEM,
    EMPTY_EXPLANATION,
    NO_PLAN_PROBLEM,
    NOT_MET_PROBLEM,
    REFUSED_PROBLEM,
    STEP_LIMIT,
    STEP_LIMIT_PROBLEM,
    SYSTEM_PROMPT,
    run_agent,
)
from degree_planner_backend.agent.request_models import EXPLANATION_MAX, AgentRequest
from degree_planner_backend.data_loader import refresh_database

# A made-up program small enough to plan by hand: TEST101 then TEST102, 6 credits in all.
PROGRAM = {
    "program_id": "tiny-bs",
    "name": "Tiny Test Major",
    "degree_level": "bachelor",
    "catalog_year": "2026-2027",
    "total_credits_required": 6,
    "requirement_groups": [
        {"group_id": "core", "label": "Core", "kind": "all", "courses": ["TEST101", "TEST102"]},
    ],
}


def make_course(code: str, **extra: object) -> dict:
    return extra | {
        "code": code,
        "subject": code[:4],
        "number": code[4:],
        "title": f"Test course {code}",
        "credits": 3.0,
        "description": "Made-up course for tests.",
        "catalog_year": "2026-2027",
    }


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    courses = [make_course("TEST101"), make_course("TEST102", prerequisites={"type": "course", "code": "TEST101"})]
    (tmp_path / "data.json").write_text(json.dumps({"courses": courses, "programs": [PROGRAM]}))
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def make_request(**changes: object) -> AgentRequest:
    fields = {
        "student": {"degree_level": "bachelor", "programs": ["tiny-bs"], "catalog_year": "2026-2027"},
        "semesters": 2,
        "start_term": "Fall 2026",
    } | changes
    return AgentRequest.model_validate(fields)


LABELS = ["Fall 2026", "Spring 2027"]
GOOD_PLAN = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2027", "courses": ["TEST102"]}]}
HALF_PLAN = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2027", "courses": []}]}


# --- the fake client --------------------------------------------------------------------------


def usage(input_tokens: int = 100, output_tokens: int = 20, cache_write: int = 0, cache_read: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_write,
        cache_read_input_tokens=cache_read,
    )


def tool_call(name: str, tool_input: object, call_id: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=call_id)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def reply(*content: SimpleNamespace, stop_reason: str | None = None, **usage_counts: int) -> SimpleNamespace:
    if stop_reason is None:
        stop_reason = "tool_use" if any(block.type == "tool_use" for block in content) else "end_turn"
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage(**usage_counts))


class FakeClient:
    """Answers each model call with the next scripted reply and keeps what each call was sent."""

    def __init__(self, *replies: SimpleNamespace, repeat_last: bool = False) -> None:
        self.replies = list(replies)
        self.repeat_last = repeat_last
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: object) -> SimpleNamespace:
        # A copy: the loop keeps appending to the same messages list after the call.
        self.calls.append(kwargs | {"messages": list(kwargs["messages"])})
        index = len(self.calls) - 1
        if index >= len(self.replies):
            if not self.repeat_last:
                raise AssertionError("the loop made more model calls than the script has replies")
            index = len(self.replies) - 1
        return self.replies[index]


def tool_results(client: FakeClient, call: int) -> list[dict]:
    """The tool results the loop sent on model call number `call` (0-based), decoded."""
    message = client.calls[call]["messages"][-1]
    assert message["role"] == "user"
    return [r | {"content": json.loads(r["content"])} for r in message["content"]]


# --- a plan that works --------------------------------------------------------------------------


def test_valid_plan_is_ok(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("check_plan", GOOD_PLAN)), reply(text("TEST101 first, then TEST102.")))
    response = run_agent(connection, make_request(), client=client)

    assert response.status == "ok"
    assert response.problems == ()
    assert response.explanation == "TEST101 first, then TEST102."
    assert [s.label for s in response.plan.semesters] == LABELS
    assert [[c.code for c in s.courses] for s in response.plan.semesters] == [["TEST101"], ["TEST102"]]
    assert response.plan.summary.requirements_met


def test_check_plan_result_reaches_the_model(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("check_plan", GOOD_PLAN, "c1")), reply(text("Done.")))
    run_agent(connection, make_request(), client=client)

    [result] = tool_results(client, 1)
    assert result["tool_use_id"] == "c1"
    assert result["is_error"] is False
    assert result["content"]["requirements_met"] is True


def test_plan_keeps_the_students_record_as_given(connection: sqlite3.Connection) -> None:
    student = {
        "degree_level": "bachelor",
        "programs": ["tiny-bs"],
        "catalog_year": "2026-2027",
        "completed_courses": [{"code": "test 101", "credits": 3.0, "term": "transfer"}],
    }
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST102"]}, {"label": "Spring 2027", "courses": []}]}
    client = FakeClient(reply(tool_call("check_plan", plan)), reply(text("Done.")))
    response = run_agent(connection, make_request(student=student), client=client)

    assert response.status == "ok"
    # Not the cleaned-up copy check_plan validates with ('TEST101').
    assert response.plan.student.completed_courses[0].code == "test 101"


# --- what the loop sends the model ---------------------------------------------------------------


def test_first_call_has_prompt_tools_and_request(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(text("Nothing to do.")))
    run_agent(connection, make_request(overrides=[{"type": "exception_claimed", "code": "test102"}]), client=client)

    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == SYSTEM_PROMPT
    assert [t["name"] for t in call["tools"]] == [
        "search_catalog", "get_prerequisites", "get_program_requirements", "get_forms", "check_plan",
    ]
    [first] = call["messages"]
    assert first["role"] == "user"
    assert json.dumps(LABELS) in first["content"]
    assert '"tiny-bs"' in first["content"]
    assert '"TEST102"' in first["content"]  # the override, cleaned up


def test_request_settings_are_the_same_every_step(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("search_catalog", {"query": "TEST"})), reply(text("Done.")))
    run_agent(connection, make_request(), client=client)

    # Anything that changed between steps would break the prompt cache.
    for key in ("model", "system", "tools", "output_config", "cache_control", "betas", "fallbacks"):
        assert client.calls[0][key] == client.calls[1][key]


def test_assistant_content_is_sent_back_whole(connection: sqlite3.Connection) -> None:
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    first = reply(thinking, tool_call("search_catalog", {"query": "TEST"}))
    client = FakeClient(first, reply(text("Done.")))
    run_agent(connection, make_request(), client=client)

    assistant = client.calls[1]["messages"][1]
    assert assistant == {"role": "assistant", "content": first.content}


def test_several_tool_calls_answered_in_one_message(connection: sqlite3.Connection) -> None:
    client = FakeClient(
        reply(
            tool_call("get_program_requirements", {"program_id": "tiny-bs"}, "a"),
            tool_call("get_prerequisites", {"code": "TEST102"}, "b"),
        ),
        reply(text("Done.")),
    )
    run_agent(connection, make_request(), client=client)

    results = tool_results(client, 1)
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    assert all(r["is_error"] is False for r in results)
    assert results[0]["content"]["program_id"] == "tiny-bs"


def test_unknown_tool_gets_an_error_naming_the_tools(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("make_plan", {})), reply(text("Done.")))
    run_agent(connection, make_request(), client=client)

    [result] = tool_results(client, 1)
    assert result["is_error"] is True
    assert "make_plan" in result["content"]["error"]
    assert "check_plan" in result["content"]["error"]


def test_tool_input_error_is_marked_as_error(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("search_catalog", {})), reply(text("Done.")))
    run_agent(connection, make_request(), client=client)

    [result] = tool_results(client, 1)
    assert result["is_error"] is True
    assert "error" in result["content"]


# --- semester labels ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "semesters",
    [
        [{"label": "Fall 2026", "courses": ["TEST101", "TEST102"]}],  # one label missing
        [{"label": "Spring 2027", "courses": ["TEST101"]}, {"label": "Fall 2026", "courses": ["TEST102"]}],  # out of order
        [{"label": "Fall 2026", "courses": ["TEST101"]}, {"label": "Spring 2028", "courses": ["TEST102"]}],  # invented
    ],
)
def test_wrong_labels_are_sent_back_to_the_model(connection: sqlite3.Connection, semesters: list) -> None:
    client = FakeClient(reply(tool_call("check_plan", {"semesters": semesters})), reply(text("Done.")))
    response = run_agent(connection, make_request(), client=client)

    [result] = tool_results(client, 1)
    assert result["is_error"] is True
    assert json.dumps(LABELS) in result["content"]["error"]
    # A rejected plan is never the one returned.
    assert response.status == "cannot_work"
    assert response.plan is None
    assert NO_PLAN_PROBLEM in response.problems


def test_last_accepted_plan_is_returned(connection: sqlite3.Connection) -> None:
    client = FakeClient(
        reply(tool_call("check_plan", GOOD_PLAN, "c1")),
        reply(tool_call("check_plan", {"semesters": "not a list"}, "c2")),
        reply(text("Done.")),
    )
    response = run_agent(connection, make_request(), client=client)

    assert tool_results(client, 2)[0]["is_error"] is True
    assert response.status == "ok"
    assert [[c.code for c in s.courses] for s in response.plan.semesters] == [["TEST101"], ["TEST102"]]


# --- plans that do not work ---------------------------------------------------------------------


def test_no_plan_at_all(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), client=FakeClient(reply(text("I could not plan this."))))

    assert response.status == "cannot_work"
    assert response.plan is None
    assert response.problems == (NO_PLAN_PROBLEM,)
    assert response.explanation == "I could not plan this."


def test_unfinished_plan_is_cannot_work_with_the_plan(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("check_plan", HALF_PLAN)), reply(text("Here is a start.")))
    response = run_agent(connection, make_request(), client=client)

    assert response.status == "cannot_work"
    assert response.plan is not None  # the planner page can still draw it
    assert not response.plan.summary.requirements_met
    assert NOT_MET_PROBLEM in response.problems


def test_unknown_course_is_a_problem(connection: sqlite3.Connection) -> None:
    plan = {"semesters": [{"label": "Fall 2026", "courses": ["TEST101", "FAKE999"]}, {"label": "Spring 2027", "courses": ["TEST102"]}]}
    client = FakeClient(reply(tool_call("check_plan", plan)), reply(text("Done.")))
    response = run_agent(connection, make_request(), client=client)

    assert response.status == "cannot_work"
    assert any("FAKE999" in problem for problem in response.problems)


def test_model_saying_done_does_not_make_a_failing_plan_ok(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("check_plan", HALF_PLAN)), reply(text("All requirements are met!")))
    response = run_agent(connection, make_request(), client=client)

    assert response.status == "cannot_work"


# --- stopping -----------------------------------------------------------------------------------


def test_step_limit_stops_the_loop(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("search_catalog", {"query": "TEST"})), repeat_last=True)
    response = run_agent(connection, make_request(), client=client)

    assert len(client.calls) == STEP_LIMIT
    assert response.usage.steps == STEP_LIMIT
    assert response.status == "cannot_work"
    assert response.problems[0] == STEP_LIMIT_PROBLEM


def test_step_limit_keeps_the_last_plan(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(tool_call("check_plan", GOOD_PLAN)), repeat_last=True)
    response = run_agent(connection, make_request(), client=client)

    # Even a passing plan is not "ok" when the agent never finished.
    assert response.status == "cannot_work"
    assert response.problems == (STEP_LIMIT_PROBLEM,)
    assert response.plan is not None
    assert response.explanation == EMPTY_EXPLANATION


def test_step_limit_can_be_changed(connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop, "STEP_LIMIT", 3)
    client = FakeClient(reply(tool_call("search_catalog", {"query": "TEST"})), repeat_last=True)
    response = run_agent(connection, make_request(), client=client)

    assert len(client.calls) == 3
    assert response.usage.steps == 3


def test_refusal_is_cannot_work(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(stop_reason="refusal"))
    response = run_agent(connection, make_request(), client=client)

    assert response.status == "cannot_work"
    assert response.problems[0] == REFUSED_PROBLEM
    assert response.explanation == EMPTY_EXPLANATION


def test_cut_off_reply_is_cannot_work_and_runs_no_tool(connection: sqlite3.Connection) -> None:
    # A tool call cut off by max_tokens can have incomplete input, so it is not run.
    client = FakeClient(reply(tool_call("check_plan", GOOD_PLAN), stop_reason="max_tokens"))
    response = run_agent(connection, make_request(), client=client)

    assert len(client.calls) == 1
    assert response.status == "cannot_work"
    assert response.problems[0] == CUT_OFF_PROBLEM
    assert response.plan is None


# --- explanation and usage ----------------------------------------------------------------------


def test_text_blocks_are_joined_into_the_explanation(connection: sqlite3.Connection) -> None:
    client = FakeClient(reply(text("First part."), text("  Second part.  ")))
    response = run_agent(connection, make_request(), client=client)

    assert response.explanation == "First part.\n\nSecond part."


@pytest.mark.parametrize("final", ["", "   ", "\n\n"])
def test_empty_final_message_gets_a_fixed_explanation(connection: sqlite3.Connection, final: str) -> None:
    response = run_agent(connection, make_request(), client=FakeClient(reply(text(final))))

    assert response.explanation == EMPTY_EXPLANATION


def test_long_explanation_is_cut_to_the_limit(connection: sqlite3.Connection) -> None:
    response = run_agent(connection, make_request(), client=FakeClient(reply(text("x" * (EXPLANATION_MAX + 50)))))

    assert len(response.explanation) == EXPLANATION_MAX


def test_usage_is_summed_over_every_step(connection: sqlite3.Connection) -> None:
    client = FakeClient(
        reply(tool_call("search_catalog", {"query": "TEST"}), input_tokens=100, output_tokens=10, cache_write=500),
        reply(text("Done."), input_tokens=40, output_tokens=30, cache_read=500),
    )
    response = run_agent(connection, make_request(), client=client)

    # Cached input counts too: 100 + 500 written, then 40 + 500 read.
    assert response.usage.model_dump() == {"input_tokens": 1140, "output_tokens": 40, "steps": 2}


def test_missing_cache_counts_are_treated_as_zero(connection: sqlite3.Connection) -> None:
    final = reply(text("Done."))
    final.usage.cache_creation_input_tokens = None
    final.usage.cache_read_input_tokens = None
    response = run_agent(connection, make_request(), client=FakeClient(final))

    assert response.usage.input_tokens == 100
