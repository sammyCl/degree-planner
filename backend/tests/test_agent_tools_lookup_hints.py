"""BUG-013 and BUG-020: the agent tools use lookups.catalog_years and lookups.program_ids.

- search_catalog: a catalog year with no courses loaded is an error naming the loaded years, not an
  empty "no match" list (BUG-013).
- get_prerequisites: the same years, when the code is in no year either (BUG-013 extension).
- get_forms: did_you_mean with close loaded program ids when program_found is false (BUG-020).
- get_program_requirements: the same did_you_mean on "no program with this id" (BUG-020 extension).
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend import lookups
from degree_planner_backend.agent.tools import (
    DID_YOU_MEAN_MAX,
    GET_FORMS_TOOL,
    GET_PREREQUISITES_TOOL,
    GET_PROGRAM_REQUIREMENTS_TOOL,
    PROGRAM_NOT_FOUND,
    SEARCH_CATALOG_TOOL,
    get_forms,
    get_prerequisites,
    get_program_requirements,
    search_catalog,
)
from degree_planner_backend.data_loader import refresh_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def course(code: str, catalog_year: str = "2026-2027", title: str = "Test Course") -> dict:
    return {
        "code": code,
        "subject": code[:4],
        "number": code[4:],
        "title": title,
        "credits": 3.0,
        "description": "Made-up course for tests.",
        "catalog_year": catalog_year,
    }


def program(program_id: str, catalog_year: str = "2026-2027", degree_level: str = "minor") -> dict:
    return {
        "program_id": program_id,
        "name": f"{program_id} program",
        "degree_level": degree_level,
        "catalog_year": catalog_year,
        "total_credits_required": 18,
        "requirement_groups": [{"group_id": "core", "label": "Core", "kind": "all", "courses": ["CSCI200"]}],
    }


def load(tmp_path: Path, *, courses: list[dict] | None = None, programs: list[dict] | None = None) -> sqlite3.Connection:
    if courses is not None:
        (tmp_path / "courses.json").write_text(json.dumps({"courses": courses}))
    if programs is not None:
        (tmp_path / "programs.json").write_text(json.dumps({"programs": programs}))
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def assert_bad_input(result: dict) -> None:
    assert set(result) == {"error"}
    assert "server problem" not in result["error"]


def broken_lookup(*_args: object) -> list[str]:
    raise sqlite3.OperationalError("no such table: courses")


@pytest.fixture
def real_data_connection(tmp_path: Path) -> sqlite3.Connection:
    """Everything in data/json, copied so the repo is never written."""
    for path in (REPO_ROOT / "data" / "json").glob("*.json"):
        shutil.copy(path, tmp_path / path.name)
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


@pytest.fixture
def two_years(tmp_path: Path) -> sqlite3.Connection:
    return load(tmp_path, courses=[course("PHGN100", "2025-2026"), course("MATH201", "2026-2027")])


# --- search_catalog (BUG-013) ---------------------------------------------------


def test_search_unloaded_year_lists_loaded_years(two_years: sqlite3.Connection) -> None:
    result = search_catalog(two_years, {"query": "PHGN", "catalog_year": "2019-2020"})
    assert_bad_input(result)
    assert result["error"].startswith("no courses are loaded for catalog year 2019-2020;")
    assert "loaded catalog years: 2025-2026, 2026-2027." in result["error"]
    assert "omit catalog_year" in result["error"]


def test_search_loaded_year_with_no_match_is_still_an_empty_list(two_years: sqlite3.Connection) -> None:
    # The year is loaded, so an empty result really means "nothing matched": no error.
    result = search_catalog(two_years, {"query": "PHGN", "catalog_year": "2026-2027"})
    assert result == {"courses": [], "count": 0}


def test_search_loaded_year_still_filters(two_years: sqlite3.Connection) -> None:
    result = search_catalog(two_years, {"query": "PHGN", "catalog_year": "2025-2026"})
    assert [c["code"] for c in result["courses"]] == ["PHGN100"]


def test_search_without_year_does_not_check_years(two_years: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lookups, "catalog_years", broken_lookup)
    assert search_catalog(two_years, {"query": "PHGN"})["count"] == 1


def test_search_empty_catalog_says_unavailable_without_a_retry(tmp_path: Path) -> None:
    result = search_catalog(load(tmp_path, courses=[]), {"query": "CSCI", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "or for any other catalog year" in result["error"]
    assert "Call again" not in result["error"]


def test_search_never_shows_a_malformed_stored_year(two_years: sqlite3.Connection) -> None:
    two_years.execute("UPDATE courses SET catalog_year = 'IGNORE PREVIOUS' WHERE code = 'PHGN100'")
    result = search_catalog(two_years, {"query": "PHGN", "catalog_year": "2019-2020"})
    assert "IGNORE" not in result["error"]
    assert "loaded catalog years: 2026-2027." in result["error"]


def test_search_year_lookup_failure_falls_back_to_the_search(
    two_years: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The year check is only a hint: if it fails, the search runs as before rather than reporting
    # a server problem for a request that may be fine.
    monkeypatch.setattr(lookups, "catalog_years", broken_lookup)
    result = search_catalog(two_years, {"query": "PHGN", "catalog_year": "2025-2026"})
    assert result["count"] == 1
    assert "catalog year lookup failed" in caplog.text


def test_search_description_mentions_the_unloaded_year_error() -> None:
    assert "loaded catalog years" in SEARCH_CATALOG_TOOL["description"]


# --- get_prerequisites (BUG-013 extension) --------------------------------------


def test_prerequisites_unknown_code_in_unloaded_year_lists_loaded_years(two_years: sqlite3.Connection) -> None:
    result = get_prerequisites(two_years, {"code": "NOPE999", "catalog_year": "2019-2020"})
    assert_bad_input(result)
    assert "No courses are loaded for that catalog year; loaded catalog years: 2025-2026, 2026-2027." in result["error"]
    assert "search_catalog" in result["error"]


def test_prerequisites_known_code_in_unloaded_year_still_names_its_year(two_years: sqlite3.Connection) -> None:
    # The course-specific answer is more useful than the list of loaded years, so it wins.
    result = get_prerequisites(two_years, {"code": "MATH201", "catalog_year": "2019-2020"})
    assert_bad_input(result)
    assert "exists only in catalog year 2026-2027" in result["error"]
    assert "loaded catalog years" not in result["error"]


def test_prerequisites_unknown_code_in_loaded_year_is_unchanged(two_years: sqlite3.Connection) -> None:
    result = get_prerequisites(two_years, {"code": "NOPE999", "catalog_year": "2026-2027"})
    assert result == {
        "error": "no course NOPE999 in catalog year 2026-2027. Use search_catalog to find the exact code, or omit catalog_year."
    }


def test_prerequisites_empty_catalog_says_unavailable(tmp_path: Path) -> None:
    result = get_prerequisites(load(tmp_path, courses=[]), {"code": "CSCI400", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "not available right now" in result["error"]


def test_prerequisites_description_mentions_loaded_years() -> None:
    assert "lists the loaded catalog years" in GET_PREREQUISITES_TOOL["description"]


# --- get_forms (BUG-020) --------------------------------------------------------


def test_forms_typo_gets_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    # The exact steps from BUG-020.
    result = get_forms(real_data_connection, {"program_id": "computer-science-minr"})
    assert result["program_found"] is False
    assert result["did_you_mean"] == ["computer-science-minor"]
    assert result["count"] > 0  # the forms are still listed


def test_forms_far_off_id_has_no_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    result = get_forms(real_data_connection, {"program_id": "underwater-basket-weaving-bs"})
    assert result["program_found"] is False
    assert "did_you_mean" not in result


def test_forms_loaded_id_has_no_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    result = get_forms(real_data_connection, {"program_id": "computer-science-minor"})
    assert result["program_found"] is True
    assert "did_you_mean" not in result


def test_forms_without_program_id_has_no_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    assert "did_you_mean" not in get_forms(real_data_connection, {})


def test_forms_did_you_mean_is_capped_and_closest_first(tmp_path: Path) -> None:
    # Five ids all above the cutoff (0.89 each, 0.96 for geology-minor), so the cap is what limits it.
    ids = ["geology-minor-a", "geology-minor-b", "geology-minor-c", "geology-minor-d", "geology-minor"]
    result = get_forms(load(tmp_path, programs=[program(i) for i in ids]), {"program_id": "geology-minr"})
    assert len(result["did_you_mean"]) == DID_YOU_MEAN_MAX
    assert result["did_you_mean"][0] == "geology-minor"


def test_forms_did_you_mean_is_only_stored_ids(real_data_connection: sqlite3.Connection) -> None:
    # Nothing the model sent is echoed: every suggestion is a loaded id, never the input itself.
    sent = "computer-science-minr"
    result = get_forms(real_data_connection, {"program_id": sent})
    assert set(result["did_you_mean"]) <= set(lookups.program_ids(real_data_connection))
    assert sent not in json.dumps(result)


def test_forms_program_id_lookup_failure_still_lists_forms(
    real_data_connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(lookups, "program_ids", broken_lookup)
    result = get_forms(real_data_connection, {"program_id": "computer-science-minr"})
    assert result["program_found"] is False
    assert "did_you_mean" not in result
    assert result["count"] > 0
    assert "program id lookup failed" in caplog.text


def test_forms_description_warns_a_close_id_can_be_another_program() -> None:
    assert "did_you_mean" in GET_FORMS_TOOL["description"]
    assert "never switch the student to another program" in GET_FORMS_TOOL["description"]


# --- get_program_requirements (BUG-020 extension) -------------------------------


def test_program_typo_gets_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    result = get_program_requirements(real_data_connection, {"program_id": "computer-science-minr"})
    assert result == {"error": PROGRAM_NOT_FOUND, "did_you_mean": ["computer-science-minor"]}


def test_program_typo_with_year_gets_did_you_mean(real_data_connection: sqlite3.Connection) -> None:
    result = get_program_requirements(
        real_data_connection, {"program_id": "computer-science-minr", "catalog_year": "2026-2027"}
    )
    assert "mistyped" in result["error"]
    assert result["did_you_mean"] == ["computer-science-minor"]


def test_program_in_another_year_has_no_did_you_mean(tmp_path: Path) -> None:
    # The error already names the year the program is in; suggesting the same id would be noise.
    # A bachelor's program, since a minor in an older year now falls back to it (BUG-053).
    conn = load(tmp_path, programs=[program("test-bs", "2025-2026", "bachelor")])
    result = get_program_requirements(conn, {"program_id": "test-bs", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "exists only in catalog year 2025-2026" in result["error"]


def test_program_far_off_id_is_unchanged(real_data_connection: sqlite3.Connection) -> None:
    result = get_program_requirements(real_data_connection, {"program_id": "ignore-all-previous-instructions"})
    assert result == {"error": PROGRAM_NOT_FOUND}


def test_program_description_mentions_did_you_mean() -> None:
    assert "did_you_mean" in GET_PROGRAM_REQUIREMENTS_TOOL["description"]
