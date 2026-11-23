"""Checks on data/json/bachelors.json, built by data/tools/build_bachelors_json.py (bachelor's data: Samantha)."""
import json
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.models import DataFile, Program

REPO_ROOT = Path(__file__).resolve().parents[2]
BACHELORS = REPO_ROOT / "data" / "json" / "bachelors.json"
COURSES = REPO_ROOT / "data" / "json" / "courses.json"

# The five programs the examples need (Samantha). The file now holds every bachelor's major (Abdallah, 2026-11-22),
# so these must be present, but they are no longer the only ones.
EXPECTED_IDS = {"cs-bs-general-track", "mining-bs", "ams-bs-cam", "ams-bs-stats", "ams-bs-ds"}
EXPECTED_TOTALS = {"cs-bs-general-track": 128, "mining-bs": 131, "ams-bs-cam": 120, "ams-bs-stats": 120, "ams-bs-ds": 120}

# Programs whose groups add up to less than the printed total, because the program PDF and the course CSV disagree on
# a course's credits (see data/CONFLICT-LOG.md, "Bachelor's programs: the remaining majors"). QBE: the PDF counts
# CBEN321 Genetics as 4.0 credits, the CSV says 3.0.
KNOWN_CREDIT_GAPS = {"qbe-bs-general": 1.0, "qbe-bs-honors": 1.0}


@pytest.fixture(scope="module")
def programs() -> list[Program]:
    return DataFile.model_validate(json.loads(BACHELORS.read_text())).programs


@pytest.fixture(scope="module")
def course_credits() -> dict[str, float]:
    return {c["code"]: c["credits"] for c in json.loads(COURSES.read_text())["courses"]}


def test_file_holds_the_example_programs_with_unique_ids(programs: list[Program]) -> None:
    ids = [p.program_id for p in programs]
    assert len(ids) == len(set(ids))
    assert EXPECTED_IDS <= set(ids)


def test_programs_are_bachelors_in_one_catalog_year(programs: list[Program]) -> None:
    for p in programs:
        assert p.degree_level == "bachelor", p.program_id
        assert p.catalog_year == "2026-2027", p.program_id
        assert p.total_credits_required > 0, p.program_id
        if p.program_id in EXPECTED_TOTALS:
            assert p.total_credits_required == EXPECTED_TOTALS[p.program_id]


def test_group_ids_unique_within_each_program(programs: list[Program]) -> None:
    for p in programs:
        ids = [g.group_id for g in p.requirement_groups]
        assert len(ids) == len(set(ids)), p.program_id


def test_every_course_code_is_in_the_catalog(programs: list[Program], course_credits: dict[str, float]) -> None:
    for p in programs:
        for g in p.requirement_groups:
            missing = [c for c in g.courses or [] if c not in course_credits]
            assert missing == [], f"{p.program_id}/{g.group_id}: {missing}"


def test_no_duplicate_codes_inside_a_group(programs: list[Program]) -> None:
    for p in programs:
        for g in p.requirement_groups:
            codes = g.courses or []
            assert len(codes) == len(set(codes)), f"{p.program_id}/{g.group_id}"


def test_group_credits_add_up_to_the_program_total(programs: list[Program], course_credits: dict[str, float]) -> None:
    for p in programs:
        total = 0.0
        for g in p.requirement_groups:
            if g.kind == "all":
                total += sum(course_credits[c] for c in g.courses or [])
            else:
                total += g.credits_required or 0.0
        assert total + KNOWN_CREDIT_GAPS.get(p.program_id, 0.0) == pytest.approx(p.total_credits_required), p.program_id


def test_required_courses_are_not_also_electives(programs: list[Program]) -> None:
    """The validator checks groups independently, so a required course on an elective list would count twice."""
    for p in programs:
        required = {c for g in p.requirement_groups if g.kind == "all" for c in g.courses or []}
        for g in p.requirement_groups:
            if g.kind == "choose_credits":
                overlap = required & set(g.courses or [])
                assert overlap == set(), f"{p.program_id}/{g.group_id}: {sorted(overlap)}"


# Groups that cannot be met yet from one pass through their list, because Independent Study is stored as 3 credits
# (data/CONFLICT-LOG.md, Course catalog) and a plan can neither take it twice (BUG-027) nor choose its credits
# (BUG-039). QBE Honors needs 6 credits of BIOL499 over two semesters. Remove an entry once those bugs are fixed.
KNOWN_UNMEETABLE_GROUPS = {("qbe-bs-honors", "honors-research")}


def test_choose_groups_can_be_met_from_their_lists(programs: list[Program], course_credits: dict[str, float]) -> None:
    for p in programs:
        for g in p.requirement_groups:
            if g.kind == "choose_credits" and g.courses:
                available = sum(course_credits[c] for c in g.courses)
                if (p.program_id, g.group_id) in KNOWN_UNMEETABLE_GROUPS:
                    # Fails once the group can be met, so the exception is not left behind after the fix.
                    assert available < (g.credits_required or 0.0), f"{p.program_id}/{g.group_id} can be met now; remove it from KNOWN_UNMEETABLE_GROUPS"
                else:
                    assert available >= (g.credits_required or 0.0), f"{p.program_id}/{g.group_id}"


def test_success_wellness_matches_the_registrar_table(programs: list[Program], course_credits: dict[str, float]) -> None:
    """https://registrar.mines.edu/core-curriculum/ 'Success & Wellness Electives': CSM202 (already required),
    CSM250, CSM275, CSM350, or any 1.0-credit PAGN 2xx course."""
    for p in programs:
        group = next(g for g in p.requirement_groups if g.group_id == "success-wellness")
        codes = set(group.courses or [])
        assert {"CSM250", "CSM275", "CSM350"} <= codes, p.program_id
        assert "CSM202" not in codes, p.program_id
        pagn = {c for c in codes if c.startswith("PAGN")}
        assert pagn, p.program_id
        assert all(c[4] == "2" and course_credits[c] == 1.0 for c in pagn), p.program_id
        assert codes - pagn == {"CSM250", "CSM275", "CSM350"}, p.program_id
        assert group.credits_required == 1


@pytest.mark.parametrize(
    ("program_id", "group_id", "codes"),
    [
        ("cs-bs-general-track", "required", {"CSCI370", "CSCI400", "CSCI406", "CSCI442"}),
        ("mining-bs", "required", {"MNGN210", "MNGN428", "MNGN429", "MNGN482"}),
        ("mining-bs", "fluid-mechanics", {"MEGN351", "PEGN251"}),
        ("ams-bs-cam", "required", {"MATH455", "MATH484"}),
        ("ams-bs-stats", "required", {"MATH437", "MATH482"}),
        ("ams-bs-ds", "required", {"CSCI470", "DSCI403"}),
    ],
)
def test_spot_check_courses_from_the_pdfs(programs: list[Program], program_id: str, group_id: str, codes: set[str]) -> None:
    program = next(p for p in programs if p.program_id == program_id)
    group = next(g for g in program.requirement_groups if g.group_id == group_id)
    assert codes <= set(group.courses or [])


def test_loader_reads_the_file(tmp_path: Path) -> None:
    (tmp_path / "bachelors.json").write_text(BACHELORS.read_text())
    conn = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, conn)
    assert report.ok, report
    ids = {p["program_id"] for p in json.loads(BACHELORS.read_text())["programs"]}
    assert report.programs_loaded == len(ids)
    rows = {r[0] for r in conn.execute("SELECT program_id FROM programs WHERE catalog_year = '2026-2027'")}
    assert rows == ids
