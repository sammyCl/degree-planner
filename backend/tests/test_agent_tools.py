import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

from degree_planner_backend.agent.tools import CATALOG_UNAVAILABLE, SEARCH_CATALOG_TOOL, search_catalog
from degree_planner_backend.data_loader import refresh_database

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "sample.json")
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


def codes(result: dict) -> list[str]:
    return [course["code"] for course in result["courses"]]


def assert_bad_input(result: dict) -> None:
    """An input error: only an error key, and not mistaken for a server problem."""
    assert set(result) == {"error"}
    assert "server problem" not in result["error"]


def test_code_match(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "MATH"})
    assert result["count"] == 2
    assert codes(result) == ["MATH201", "MATH223"]


def test_title_match_any_case(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "rock mechanics"})
    assert codes(result) == ["MNGN502"]


def test_returns_only_short_fields(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "CSCI306"})
    assert result["count"] == 1
    assert set(result["courses"][0]) == {"code", "title", "credits", "catalog_year"}


def test_no_match_is_empty_not_error(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "basket weaving"})
    assert result == {"courses": [], "count": 0}


def test_catalog_year_filter(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "MATH", "catalog_year": "2019-2020"})
    assert result["count"] == 0


def test_limit(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "MNGN", "limit": 1})
    assert codes(result) == ["MNGN501"]


@pytest.mark.parametrize("tool_input", [{"query": "  "}, {}])
def test_empty_or_missing_query_returns_error(connection: sqlite3.Connection, tool_input: dict) -> None:
    result = search_catalog(connection, tool_input)
    assert_bad_input(result)


@pytest.mark.parametrize("limit", [0, 51])
def test_bad_limit_returns_error(connection: sqlite3.Connection, limit: int) -> None:
    result = search_catalog(connection, {"query": "MATH", "limit": limit})
    assert_bad_input(result)


def test_tool_definition() -> None:
    assert SEARCH_CATALOG_TOOL["name"] == "search_catalog"
    assert SEARCH_CATALOG_TOOL["input_schema"]["required"] == ["query"]


# Odd input types: what a model might send instead of a clean integer or string.


@pytest.mark.parametrize("limit", ["5", 5.0, True])
def test_limit_wrong_type_returns_error(connection: sqlite3.Connection, limit: object) -> None:
    result = search_catalog(connection, {"query": "MATH", "limit": limit})
    assert_bad_input(result)


def test_catalog_year_wrong_type_returns_error(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "MATH", "catalog_year": 2026})
    assert_bad_input(result)


# Year filter, matching case: the filter keeps courses, not only drops them.


def test_catalog_year_filter_matching_year(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, {"query": "MATH", "catalog_year": "2026-2027"})
    assert codes(result) == ["MATH201", "MATH223"]


# Made-up catalogs for the tests below, loaded the same way as the sample data.


def make_course(code: str, catalog_year: str = "2026-2027", title: str = "Test Course") -> dict:
    subject, number = code[:4], code[4:]
    return {
        "code": code,
        "subject": subject,
        "number": number,
        "title": title,
        "credits": 3.0,
        "description": "Made-up course for tests.",
        "catalog_year": catalog_year,
    }


def load_courses(tmp_path: Path, courses: list[dict]) -> sqlite3.Connection:
    (tmp_path / "courses.json").write_text(json.dumps({"courses": courses}))
    conn = sqlite3.connect(":memory:")
    refresh_database(tmp_path, conn)
    return conn


# Two catalog years: the same course code exists in both.


@pytest.fixture
def two_year_connection(tmp_path: Path) -> sqlite3.Connection:
    return load_courses(
        tmp_path,
        [
            make_course("PHGN100", "2025-2026", "Physics I"),
            make_course("PHGN100", "2026-2027", "Physics I - Mechanics"),
        ],
    )


def test_two_years_unfiltered_returns_both(two_year_connection: sqlite3.Connection) -> None:
    result = search_catalog(two_year_connection, {"query": "PHGN100"})
    assert result["count"] == 2
    assert sorted(course["catalog_year"] for course in result["courses"]) == ["2025-2026", "2026-2027"]


def test_two_years_filter_keeps_one(two_year_connection: sqlite3.Connection) -> None:
    result = search_catalog(two_year_connection, {"query": "PHGN100", "catalog_year": "2025-2026"})
    assert result["count"] == 1
    assert result["courses"][0]["title"] == "Physics I"


# Default limit: 25 matching courses, more than the default of 20.


@pytest.fixture
def many_courses_connection(tmp_path: Path) -> sqlite3.Connection:
    return load_courses(tmp_path, [make_course(f"TEST{n:03d}") for n in range(1, 26)])


def test_default_limit_is_20(many_courses_connection: sqlite3.Connection) -> None:
    result = search_catalog(many_courses_connection, {"query": "TEST"})
    assert result["count"] == 20
    assert codes(result)[0] == "TEST001"
    assert codes(result)[-1] == "TEST020"


def test_limit_50_returns_all_25(many_courses_connection: sqlite3.Connection) -> None:
    result = search_catalog(many_courses_connection, {"query": "TEST", "limit": 50})
    assert result["count"] == 25


# Bug fix: tool input that is not a dict returns an error instead of raising.


@pytest.mark.parametrize("tool_input", [None, "MATH", ["MATH"], 42])
def test_non_dict_input_returns_error(connection: sqlite3.Connection, tool_input: object) -> None:
    result = search_catalog(connection, tool_input)  # type: ignore[arg-type]
    assert_bad_input(result)
    assert "object" in result["error"]


# Bug fix: a lone surrogate (valid JSON escape, not encodable text) is bad input, not a crash.


@pytest.mark.parametrize("field", ["query", "catalog_year"])
def test_lone_surrogate_returns_error(connection: sqlite3.Connection, field: str) -> None:
    tool_input = json.loads('{"query": "MATH", "%s": "\\ud800"}' % field)
    assert_bad_input(search_catalog(connection, tool_input))


# Bug fix: database failures return one fixed message: server problem, do not retry,
# with no internals for the model. The real exception goes to the log instead.


def assert_catalog_unavailable(result: dict) -> None:
    assert result == {"error": CATALOG_UNAVAILABLE}
    assert "server problem" in result["error"]
    assert "do not retry" in result["error"]


def test_database_without_tables_returns_error(caplog: pytest.LogCaptureFixture) -> None:
    conn = sqlite3.connect(":memory:")
    result = search_catalog(conn, {"query": "MATH"})
    conn.close()
    assert_catalog_unavailable(result)
    assert "no such table" not in result["error"]
    assert "no such table" in caplog.text


def test_closed_connection_returns_error(connection: sqlite3.Connection) -> None:
    connection.close()
    assert_catalog_unavailable(search_catalog(connection, {"query": "MATH"}))


def test_other_thread_hides_thread_ids(connection: sqlite3.Connection) -> None:
    results: list[dict] = []
    worker = threading.Thread(target=lambda: results.append(search_catalog(connection, {"query": "MATH"})))
    worker.start()
    worker.join()
    assert_catalog_unavailable(results[0])
    assert "thread" not in results[0]["error"]


def test_malformed_course_row_returns_error(connection: sqlite3.Connection, caplog: pytest.LogCaptureFixture) -> None:
    connection.execute("INSERT INTO courses (code, catalog_year, data) VALUES ('BAD100', '2026-2027', '{}')")
    result = search_catalog(connection, {"query": "MATH"})
    assert_catalog_unavailable(result)
    assert "malformed" in caplog.text
