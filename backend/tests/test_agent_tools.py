import shutil
import sqlite3
from pathlib import Path

import pytest

from degree_planner_backend.agent.tools import SEARCH_CATALOG_TOOL, search_catalog
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
    assert "error" in result


@pytest.mark.parametrize("limit", [0, 51])
def test_bad_limit_returns_error(connection: sqlite3.Connection, limit: int) -> None:
    result = search_catalog(connection, {"query": "MATH", "limit": limit})
    assert "error" in result


def test_tool_definition() -> None:
    assert SEARCH_CATALOG_TOOL["name"] == "search_catalog"
    assert SEARCH_CATALOG_TOOL["input_schema"]["required"] == ["query"]
