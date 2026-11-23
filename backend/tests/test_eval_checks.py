"""Tests for agent/eval_checks.py: example files and the deterministic checks (agent/eval: Samantha).
Plans are written by hand; nothing here calls a model."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from degree_planner_backend.agent.eval_checks import (
    EXAMPLES_DIR,
    Example,
    deterministic_verdict,
    load_examples,
)
from degree_planner_backend.agent.request_models import AgentResponse, Usage
from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.plan_models import Plan, PlannedCourse, Semester, Student, Summary

REPO_ROOT = Path(__file__).resolve().parents[2]

BASE = {
    "id": 9,
    "name": "test example",
    "difficulty": "simple",
    "request": {
        "student": {"degree_level": "bachelor", "programs": ["t-major"], "catalog_year": "2026-2027",
                    "completed_courses": [{"code": "MATH111", "credits": 4.0, "term": "transfer"}]},
        "semesters": 3,
        "start_term": "Fall 2026",
        "include_summers": False,
        "overrides": [],
    },
    "also_must": [],
}
LABELS = ["Fall 2026", "Spring 2027", "Fall 2027"]


def example(*checks: dict, **request_changes: object) -> Example:
    data = copy.deepcopy(BASE)
    data["also_must"] = list(checks)
    data["request"].update(request_changes)
    return Example.model_validate(data)


def response(semesters: dict[str, list[tuple[str, float]]] | None, status: str = "ok",
             problems: tuple[str, ...] = ()) -> AgentResponse:
    plan = None
    if semesters is not None:
        plan = Plan(
            student=Student(degree_level="bachelor", programs=["t-major"], catalog_year="2026-2027"),
            semesters=[
                Semester(semester_id=f"s{i}", label=label,
                         courses=[PlannedCourse(course_id=f"{label}-{code}", code=code, title=code, credits=credits,
                                                status="planned") for code, credits in semesters.get(label, [])])
                for i, label in enumerate(LABELS)
            ],
            summary=Summary(total_credits=0, total_credits_required=0, requirements_met=status == "ok"),
        )
    return AgentResponse(status=status, plan=plan, explanation="test", problems=problems,
                         usage=Usage(input_tokens=0, output_tokens=0, steps=0))


def run(conn: sqlite3.Connection | None, ex: Example, resp: AgentResponse) -> dict[str, bool]:
    verdict = deterministic_verdict(conn, ex, resp)  # type: ignore[arg-type]
    return {r.type: r.passed for r in verdict.results}


PLAN = {
    "Fall 2026": [("CSCI128", 3.0), ("MATH112", 4.0), ("EENG500", 0.0)],
    "Spring 2027": [("CSCI200", 3.0), ("CSCI370", 5.0), ("EENG500", 0.0)],
    "Fall 2027": [("CSCI220", 3.0), ("CSCI210", 3.0), ("EENG500", 0.0)],
}


# ------------------------------------------------------------------------------- example files

def test_the_repository_examples_load() -> None:
    examples = load_examples()
    ids = [e.id for e in examples]
    assert {1, 2, 3, 4} <= set(ids)
    assert ids == sorted(ids)
    # Example 5 is private (gitignored), so it is checked only where the file exists.
    if (EXAMPLES_DIR / "private").is_dir() and any((EXAMPLES_DIR / "private").glob("*.json")):
        assert 5 in ids
        assert next(e for e in examples if e.id == 5).needs_review == "Sammy"


def test_flowchart_of_example_1_has_25_courses_and_needs_20() -> None:
    ex1 = next(e for e in load_examples() if e.id == 1)
    chart = next(c for c in ex1.also_must if c.type == "flowchart_match")
    assert sum(len(v) for v in chart.flowchart.values()) == 25
    assert chart.min_matched == 20
    assert not any("CSCI370" in v for v in chart.flowchart.values())


@pytest.mark.parametrize("bad", [
    {"type": "no_such_check"},
    {"type": "not_planned", "codes": ["X"], "extra": 1},
    {"type": "not_planned", "codes": []},
    {"type": "course_in_semester", "code": "CSCI370", "semester": "Summer 2027"},
    {"type": "course_in_semester", "code": "CSCI370", "semesters": ["Fall 2026", "Summer 2027"]},
    {"type": "course_in_semester", "code": "CSCI370", "semester": "Fall 2026", "semesters": ["Fall 2026"]},
    {"type": "course_in_semester", "code": "CSCI370", "semesters": []},
    {"type": "course_in_semester", "code": "CSCI370"},
    {"type": "max_semester_credits", "limit": 18, "through": "Spring 2031"},
    {"type": "flowchart_match", "flowchart": {"Fall 2030": ["MATH111"]}, "tolerance": 1, "min_matched": 1},
    {"type": "credits_from", "codes": ["A"], "equals": 6, "max": 6},
    {"type": "credits_from", "codes": ["A"]},
])
def test_bad_checks_are_rejected_when_loaded(bad: dict) -> None:
    with pytest.raises(ValidationError):
        example(bad)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(BASE))
    with pytest.raises(ValueError, match="share an id"):
        load_examples(tmp_path)


def test_private_examples_are_read_too(tmp_path: Path) -> None:
    (tmp_path / "private").mkdir()
    (tmp_path / "a.json").write_text(json.dumps(BASE | {"id": 2}))
    (tmp_path / "private" / "b.json").write_text(json.dumps(BASE | {"id": 1}))
    assert [e.id for e in load_examples(tmp_path)] == [1, 2]


# ------------------------------------------------------------------------- status and plan

def test_cannot_work_fails_with_its_problems() -> None:
    verdict = deterministic_verdict(None, example(), response(PLAN, status="cannot_work", problems=("too short",)))  # type: ignore[arg-type]
    assert not verdict.passed
    assert "too short" in verdict.failures[0].detail


def test_no_plan_fails_every_check() -> None:
    result = run(None, example({"type": "not_planned", "codes": ["X"]}),
                 response(None, status="cannot_work", problems=("no plan",)))
    assert result == {"validator_ok": False, "not_planned": False}


def test_review_required_is_not_decided_here() -> None:
    verdict = deterministic_verdict(None, example({"type": "review_required", "by": "Sammy"}), response(PLAN))  # type: ignore[arg-type]
    assert verdict.passed
    assert [r.type for r in verdict.results] == ["validator_ok"]


# ------------------------------------------------------------------------------- each check

@pytest.mark.parametrize("check, passes", [
    ({"type": "max_semester_credits", "limit": 8}, True),
    ({"type": "max_semester_credits", "limit": 7}, False),  # Spring 2027 has 8
    ({"type": "max_semester_credits", "limit": 7, "from": "Fall 2027"}, True),
    ({"type": "max_semester_credits", "limit": 6, "through": "Fall 2026"}, False),  # Fall 2026 has 7
    ({"type": "course_in_semester", "code": "CSCI370", "semester": "Spring 2027"}, True),
    ({"type": "course_in_semester", "code": "CSCI370", "semester": "Fall 2027"}, False),
    ({"type": "course_in_semester", "code": "CSCI999", "semester": "Fall 2027"}, False),
    ({"type": "course_in_semester", "code": "CSCI370", "semesters": ["Spring 2027", "Fall 2027"]}, True),
    ({"type": "course_in_semester", "code": "CSCI370", "semesters": ["Fall 2026", "Fall 2027"]}, False),
    ({"type": "not_planned", "codes": ["HNRS105", "HNRS115"]}, True),
    ({"type": "not_planned", "codes": ["HNRS105", "CSCI200"]}, False),
    ({"type": "planned_credits", "equals": 21}, True),
    ({"type": "planned_credits", "equals": 24}, False),
    ({"type": "in_every_semester", "code": "EENG500"}, True),
    ({"type": "in_every_semester", "code": "CSCI200"}, False),
    ({"type": "count_planned", "codes": ["CSCI200", "CSCI210", "CSCI400"], "exactly": 2}, True),
    ({"type": "count_planned", "codes": ["CSCI200", "CSCI210", "CSCI400"], "exactly": 1}, False),
    ({"type": "credits_from", "codes": ["CSCI200", "CSCI210"], "equals": 6}, True),
    ({"type": "credits_from", "codes": ["CSCI200", "CSCI210"], "through": "Spring 2027", "equals": 6}, False),
    ({"type": "credits_from", "codes": ["CSCI200", "CSCI210"], "through": "Spring 2027", "max": 3}, True),
    ({"type": "credits_from", "codes": ["CSCI200", "CSCI210"], "max": 5}, False),
])
def test_each_check(check: dict, passes: bool) -> None:
    assert run(None, example(check), response(PLAN))[check["type"]] is passes


def test_completed_not_planned() -> None:
    ex = example({"type": "completed_not_planned"})
    assert run(None, ex, response(PLAN))["completed_not_planned"] is True
    again = PLAN | {"Fall 2027": [("MATH111", 4.0)]}
    assert run(None, ex, response(again))["completed_not_planned"] is False


def test_flowchart_match_counts_courses_within_the_tolerance() -> None:
    chart = {"Fall 2026": ["CSCI128", "CSCI200"], "Spring 2027": ["CSCI210"], "Fall 2027": ["CSCI400"]}
    # CSCI128 exact, CSCI200 one late, CSCI210 one late, CSCI400 not planned: 3 of 4 within 1.
    three = {"type": "flowchart_match", "flowchart": chart, "tolerance": 1, "min_matched": 3}
    assert run(None, example(three), response(PLAN))["flowchart_match"] is True
    assert run(None, example(three | {"min_matched": 4}), response(PLAN))["flowchart_match"] is False
    # With no tolerance only CSCI128 is in place.
    exact = three | {"tolerance": 0, "min_matched": 2}
    verdict = deterministic_verdict(None, example(exact), response(PLAN))  # type: ignore[arg-type]
    assert not verdict.passed
    assert "1 of 4" in verdict.failures[0].detail


# --------------------------------------------------------------------- minor_unshared_credits

def minor_db(tmp_path: Path) -> sqlite3.Connection:
    """A major and an 18-credit minor that overlap on A100 (major "all"), C100 (major choose group)."""
    def course(code: str) -> dict:
        return {"code": code, "subject": code[:1] + "AAA", "number": code[1:], "title": code, "credits": 3.0,
                "description": "", "catalog_year": "2026-2027"}

    codes = ["A100", "B100", "C100", "D100", "E100", "F100", "G100", "H100", "J100"]
    programs = [
        {"program_id": "t-major", "name": "Major", "degree_level": "bachelor", "catalog_year": "2026-2027",
         "total_credits_required": 30, "requirement_groups": [
             {"group_id": "req", "label": "req", "kind": "all", "courses": ["A100", "B100"]},
             {"group_id": "pick", "label": "pick", "kind": "choose_credits", "courses": ["C100", "D100"],
              "credits_required": 3},
             {"group_id": "free", "label": "free", "kind": "choose_credits", "credits_required": 6}]},
        {"program_id": "t-minor", "name": "Minor", "degree_level": "minor", "catalog_year": "2026-2027",
         "total_credits_required": 18, "requirement_groups": [
             {"group_id": "core", "label": "core", "kind": "all", "courses": ["A100", "E100"]},
             {"group_id": "pick", "label": "pick", "kind": "choose_credits", "courses": ["C100", "F100", "G100"],
              "credits_required": 6},
             {"group_id": "any", "label": "any", "kind": "choose_credits", "credits_required": 6}]},
    ]
    (tmp_path / "courses.json").write_text(json.dumps({"courses": [course(c) for c in codes]}))
    (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    assert refresh_database(tmp_path, conn).ok
    return conn


MINOR_CHECK = {"type": "minor_unshared_credits", "minor": "t-minor", "major": "t-major", "min": 9}


def test_minor_with_enough_unshared_credits_passes(tmp_path: Path) -> None:
    conn = minor_db(tmp_path)
    # Minor: A100 (shared) and E100; pick: F100 and G100 (unshared, preferred); any: H100 and J100 (taken in code order).
    plan = {"Fall 2026": [("A100", 3), ("B100", 3), ("D100", 3)], "Spring 2027": [("E100", 3), ("F100", 3), ("G100", 3)],
            "Fall 2027": [("H100", 3), ("J100", 3)]}
    verdict = deterministic_verdict(conn, example(MINOR_CHECK), response(plan))
    assert verdict.passed, verdict.results
    assert "15 minor credits not shared" in verdict.results[-1].detail


def test_minor_built_from_major_courses_fails(tmp_path: Path) -> None:
    conn = minor_db(tmp_path)
    # C100 is the only course in the major's pick group, so the major needs it: shared. The minor's
    # "any" group can only take B100 (major "all"), so A100, C100, B100 are shared and only E100, F100 are not.
    # No completed courses: a completed course the major does not list would fill "any" unshared.
    ex = example(MINOR_CHECK, student={"degree_level": "bachelor", "programs": ["t-major", "t-minor"],
                                       "catalog_year": "2026-2027", "completed_courses": []})
    plan = {"Fall 2026": [("A100", 3), ("B100", 3), ("C100", 3)], "Spring 2027": [("E100", 3), ("F100", 3)]}
    verdict = deterministic_verdict(conn, ex, response(plan))
    result = verdict.results[-1]
    assert not result.passed
    assert "6 minor credits not shared" in result.detail
    assert "A100, B100, C100" in result.detail


def test_a_course_the_major_does_not_need_is_not_shared(tmp_path: Path) -> None:
    conn = minor_db(tmp_path)
    # D100 fills the major's pick group, so C100 is spare and counts as unshared for the minor.
    plan = {"Fall 2026": [("A100", 3), ("B100", 3), ("C100", 3), ("D100", 3)], "Spring 2027": [("E100", 3), ("F100", 3)]}
    result = deterministic_verdict(conn, example(MINOR_CHECK), response(plan)).results[-1]
    assert result.passed, result.detail


def test_completed_courses_count_for_the_minor(tmp_path: Path) -> None:
    conn = minor_db(tmp_path)
    ex = example(MINOR_CHECK, student={"degree_level": "bachelor", "programs": ["t-major", "t-minor"],
                                       "catalog_year": "2026-2027",
                                       "completed_courses": [{"code": "G100", "credits": 3.0, "term": "transfer"}]})
    plan = {"Fall 2026": [("A100", 3), ("B100", 3), ("D100", 3)], "Spring 2027": [("E100", 3), ("F100", 3)]}
    result = deterministic_verdict(conn, ex, response(plan)).results[-1]
    assert result.passed, result.detail  # E100, F100, G100 unshared


def test_example_4_overlap_on_the_real_data_fails(tmp_path: Path) -> None:
    """The overlap BUG-036 describes: a CS minor made of AMS CAM courses breaks the 9-credit rule."""
    conn = sqlite3.connect(":memory:")
    assert refresh_database(REPO_ROOT / "data" / "json", conn).ok
    check = {"type": "minor_unshared_credits", "minor": "computer-science-minor", "major": "ams-bs-cam", "min": 9}
    plan = {"Fall 2026": [("CSCI200", 3), ("MATH334", 3)], "Spring 2027": [("MATH307", 3), ("CSCI220", 3)],
            "Fall 2027": [("CSCI210", 3), ("CSCI403", 3)]}
    result = deterministic_verdict(conn, example(check), response(plan)).results[-1]
    assert not result.passed, result.detail
    assert "CSCI200" in result.detail and "MATH334" in result.detail and "MATH307" in result.detail
