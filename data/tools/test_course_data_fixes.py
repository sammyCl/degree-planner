"""Regression tests for hand-corrected course data in data/json/courses.json.

Each test pins one fix logged in bugs.txt, so a rebuild or re-scrape that brings the old data back fails here.
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
