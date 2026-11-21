import json
import shutil
import sqlite3
from pathlib import Path

from degree_planner_backend.data_loader import refresh_database

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADUATE_PROGRAMS_JSON = REPO_ROOT / "data" / "json" / "graduate-programs.json"
COURSES_JSON = REPO_ROOT / "data" / "json" / "courses.json"


def test_graduate_programs_json_loads_with_no_errors(tmp_path: Path) -> None:
    shutil.copy(GRADUATE_PROGRAMS_JSON, tmp_path / "graduate-programs.json")

    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)

    assert report.ok
    assert report.programs_loaded == 56

    program_ids = {
        row[0] for row in connection.execute("SELECT program_id FROM programs").fetchall()
    }
    assert program_ids >= {
        "ee-ms",
        "mining-ms",
        "mining-bs-ms-combined",
        "cs-ms-non-thesis-project-track",
        "cs-bs-ms-combined",
    }
    assert len(program_ids) == report.programs_loaded  # no duplicate program_ids


def test_combined_programs_name_their_component_programs() -> None:
    data = json.loads(GRADUATE_PROGRAMS_JSON.read_text())
    programs = {p["program_id"]: p for p in data["programs"]}

    assert programs["mining-bs-ms-combined"]["combines"] == ["mining-bs", "mining-ms"]
    assert programs["cs-bs-ms-combined"]["combines"] == ["cs-bs-general-track", "cs-ms-non-thesis-project-track"]


def test_masters_programs_in_combined_degrees_cap_double_counted_credits_at_six() -> None:
    data = json.loads(GRADUATE_PROGRAMS_JSON.read_text())
    programs = {p["program_id"]: p for p in data["programs"]}

    for program_id, shares_with in [("mining-ms", "mining-bs"), ("cs-ms-non-thesis-project-track", "cs-bs-general-track")]:
        double_counts = programs[program_id]["double_counts_with"]
        assert len(double_counts) == 1
        assert double_counts[0]["program_id"] == shares_with
        assert double_counts[0]["shared_credit_limit"] == 6


def test_every_referenced_course_code_exists_in_the_course_catalog() -> None:
    programs = json.loads(GRADUATE_PROGRAMS_JSON.read_text())["programs"]
    courses = {c["code"] for c in json.loads(COURSES_JSON.read_text())["courses"]}

    unknown = {
        (program["program_id"], group["group_id"], code)
        for program in programs
        for group in program["requirement_groups"]
        for code in (group.get("courses") or [])
        if code not in courses
    }
    assert not unknown


def test_no_duplicate_program_ids() -> None:
    programs = json.loads(GRADUATE_PROGRAMS_JSON.read_text())["programs"]
    ids = [p["program_id"] for p in programs]
    assert len(ids) == len(set(ids))


def test_each_masters_program_requirement_groups_sum_to_its_total_credits() -> None:
    data = json.loads(GRADUATE_PROGRAMS_JSON.read_text())
    programs = {p["program_id"]: p for p in data["programs"]}

    # The MS project/seminar courses that count toward the "all" groups below, for the sum check.
    all_group_credits = {
        "ee-ms": {"seminar": 0.0},
        "mining-ms": {"seminar": 1.0},
        "cs-ms-non-thesis-project-track": {"core": 6.0},
    }

    for program_id, fixed_credits in all_group_credits.items():
        program = programs[program_id]
        total = sum(
            fixed_credits[g["group_id"]] if g["kind"] == "all" else g["credits_required"]
            for g in program["requirement_groups"]
        )
        assert total == program["total_credits_required"]
