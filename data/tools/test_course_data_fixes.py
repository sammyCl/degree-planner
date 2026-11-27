"""Regression tests for hand-corrected data in data/json (courses.json, bachelors.json).

Each test pins one fix logged in bugs.txt or data/CONFLICT-LOG.md, so a rebuild or re-scrape that brings the old data back fails here.
Run from backend/: uv run pytest ../data/tools
"""

import json
from pathlib import Path

COURSES = Path(__file__).resolve().parents[1] / "json" / "courses.json"


def course(code):
    data = json.loads(COURSES.read_text(encoding="utf-8"))
    entries = data["courses"] if isinstance(data, dict) else data
    matches = [c for c in entries if c["code"] == code]
    assert len(matches) == 1, f"{code}: expected one entry, found {len(matches)}"
    return matches[0]


def test_bug_047_csci478_prerequisite_is_one_of_three_courses():
    # Catalog page: "CSCI101 or CSCI102 or CSCI128". The CSV had dropped the second "or", so the parser kept
    # the text as an exception and every plan with CSCI478 got an exception warning.
    assert course("CSCI478")["prerequisites"] == {
        "type": "OR",
        "of": [
            {"type": "course", "code": "CSCI101"},
            {"type": "course", "code": "CSCI102"},
            {"type": "course", "code": "CSCI128"},
        ],
    }


def test_mining_bs_special_topics_slot_is_only_mngn298():
    # The agent planned MNGN299 Independent Study for "MNGN2XX New Special Topics" (eval ex3,
    # 2026-11-23) because the slot allowed every 200-level MNGN course. Only MNGN298 Special Topics
    # in Mining Engineering counts (Samantha, 2026-11-25; CONFLICT-LOG Bachelor's 18).
    bachelors = json.loads((COURSES.parent / "bachelors.json").read_text(encoding="utf-8"))
    mining = next(p for p in bachelors["programs"] if p["program_id"] == "mining-bs")
    slot = next(g for g in mining["requirement_groups"] if g["group_id"] == "mngn-2xx")
    assert slot["courses"] == ["MNGN298"]
    assert slot["credits_required"] == 3


def test_bug_048_course_substitution_form_is_listed():
    # Source: data/Policies/Academic Regulations and Standards.pdf, "Course Substitutions". The catalog says the
    # forms are available in the Registrar's Office and prints no link or form title, so the entry has no url.
    forms = json.loads((COURSES.parent / "forms-policies.json").read_text(encoding="utf-8"))["forms"]
    matches = [f for f in forms if f["form_id"] == "course-substitution"]
    assert len(matches) == 1
    form = matches[0]
    assert form["applies_to"] == ["any"]
    for approver in ("Registrar", "heads of departments of the two courses", "option department"):
        assert approver in form["requires"]
    assert "Registrar's Office" in form["notes"]
    assert "url" not in form
