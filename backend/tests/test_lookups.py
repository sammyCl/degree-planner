import shutil
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.lookups import (
    AmbiguousLookupError,
    NotFoundError,
    get_course,
    get_forms,
    get_prerequisites,
    get_program,
    get_program_requirements,
    search_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "sample.json")
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def test_get_course_returns_credits(connection: sqlite3.Connection) -> None:
    course = get_course(connection, "MATH201")
    assert course.credits == 3.0
    assert course.title == "Introduction to Statistics"


def test_get_course_missing_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        get_course(connection, "NOPE999")


def test_get_prerequisites_resolves_nested_and_or(connection: sqlite3.Connection) -> None:
    prerequisites = get_prerequisites(connection, "CSCI400")
    assert prerequisites.type == "AND"
    assert prerequisites.of[0].code == "CSCI306"
    assert prerequisites.of[1].type == "OR"


def test_get_prerequisites_none_when_course_has_none(connection: sqlite3.Connection) -> None:
    assert get_prerequisites(connection, "MNGN502") is None


def test_get_program_requirements_returns_groups(connection: sqlite3.Connection) -> None:
    groups = get_program_requirements(connection, "cs-bs-general-track")
    assert [group.group_id for group in groups] == ["core", "math_science", "free_electives"]
    assert groups[0].courses == ["CSCI200", "CSCI306", "CSCI400"]


def test_get_program_missing_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        get_program(connection, "no-such-program")


def test_ambiguous_catalog_year_requires_disambiguation(tmp_path: Path) -> None:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "2026.json")
    other_year = (tmp_path / "2026.json").read_text().replace("2026-2027", "2027-2028")
    (tmp_path / "2027.json").write_text(other_year)

    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)

    with pytest.raises(AmbiguousLookupError):
        get_course(conn, "MATH201")

    course = get_course(conn, "MATH201", catalog_year="2027-2028")
    assert course.catalog_year == "2027-2028"


def test_search_catalog_matches_code_and_title(connection: sqlite3.Connection) -> None:
    results = search_catalog(connection, "software engineering")
    assert [course.code for course in results] == ["CSCI306"]

    results = search_catalog(connection, "MATH")
    assert {course.code for course in results} == {"MATH201", "MATH223"}


def test_get_forms_filters_by_program(connection: sqlite3.Connection) -> None:
    all_forms = get_forms(connection)
    assert [form.form_id for form in all_forms] == ["independent-study-credit"]

    forms_for_program = get_forms(connection, program_id="cs-bs-general-track")
    assert len(forms_for_program) == 1

    forms_for_missing_program = get_forms(connection, program_id="nonexistent")
    # "independent-study-credit" applies to ["any"], so it still matches.
    assert len(forms_for_missing_program) == 1
