import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

from degree_planner_backend.agent.tools import (
    _CATALOG_YEAR_MESSAGE,
    CATALOG_UNAVAILABLE,
    GET_PREREQUISITES_TOOL,
    SEARCH_CATALOG_TOOL,
    get_prerequisites,
    LABEL_MAX,
    clean_label,
    search_catalog,
    summarize_requirement,
)
from degree_planner_backend.data_loader import refresh_database
from degree_planner_backend.models import AndRequirement, CourseRequirement, ExceptionRequirement, OrRequirement

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


def make_course(code: str, catalog_year: str = "2026-2027", title: str = "Test Course", **extra: object) -> dict:
    subject, number = code[:4], code[4:]
    return extra | {
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


# --- get_prerequisites ----------------------------------------------------------


def test_prerequisites_nested_and_or(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "CSCI400"})
    assert result["code"] == "CSCI400"
    assert result["catalog_year"] == "2026-2027"
    assert result["summary"] == "CSCI306 AND (MATH201 OR MATH223)"
    assert result["prerequisites"] == {
        "type": "AND",
        "of": [
            {"type": "course", "code": "CSCI306"},
            {"type": "OR", "of": [{"type": "course", "code": "MATH201"}, {"type": "course", "code": "MATH223"}]},
        ],
    }
    assert result["corequisites"] == []


def test_prerequisites_single_course(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "MATH201"})
    assert result["prerequisites"] == {"type": "course", "code": "MATH112"}
    assert result["summary"] == "MATH112"


def test_prerequisites_exception(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "MNGN501"})
    assert result["prerequisites"] == {"type": "exception", "label": "instructor approval"}
    assert result["summary"] == 'exception: "instructor approval"'


def test_prerequisites_none(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "MNGN502"})
    assert result["prerequisites"] is None
    assert result["summary"] == "none"


def test_prerequisites_result_fields(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "CSCI306"})
    assert set(result) == {"code", "catalog_year", "prerequisites", "summary", "corequisites"}


@pytest.mark.parametrize("code", ["csci400", "CSCI 400", "Csci-400", "  CSCI400 "])
def test_prerequisites_code_is_normalized(connection: sqlite3.Connection, code: str) -> None:
    assert get_prerequisites(connection, {"code": code})["code"] == "CSCI400"


def test_prerequisites_corequisites(tmp_path: Path) -> None:
    conn = load_courses(
        tmp_path,
        [
            make_course("PHGN100", title="Physics I", corequisites=["MATH111"]),
            make_course("MATH111", title="Calculus I"),
        ],
    )
    result = get_prerequisites(conn, {"code": "PHGN100"})
    assert result["corequisites"] == ["MATH111"]
    assert result["summary"] == "none"


def test_prerequisites_not_found(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "NOPE999"})
    assert_bad_input(result)
    assert "NOPE999" in result["error"]
    assert "search_catalog" in result["error"]


def test_prerequisites_several_years_asks_for_year(two_year_connection: sqlite3.Connection) -> None:
    result = get_prerequisites(two_year_connection, {"code": "PHGN100"})
    assert_bad_input(result)
    assert "2025-2026" in result["error"]
    assert "2026-2027" in result["error"]
    assert "catalog_year" in result["error"]


def test_prerequisites_year_picks_that_year(two_year_connection: sqlite3.Connection) -> None:
    result = get_prerequisites(two_year_connection, {"code": "PHGN100", "catalog_year": "2025-2026"})
    assert result["catalog_year"] == "2025-2026"


def test_prerequisites_wrong_year_names_the_real_year(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "CSCI400", "catalog_year": "2019-2020"})
    assert_bad_input(result)
    assert "2019-2020" in result["error"]
    assert "exists only in catalog year 2026-2027" in result["error"]
    assert "search_catalog" not in result["error"]


def test_prerequisites_wrong_year_unknown_code(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "NOPE999", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "search_catalog" in result["error"]
    assert "omit catalog_year" in result["error"]


def test_prerequisites_wrong_year_code_in_several_other_years(tmp_path: Path) -> None:
    conn = load_courses(tmp_path, [make_course("PHGN100", "2024-2025"), make_course("PHGN100", "2025-2026")])
    result = get_prerequisites(conn, {"code": "PHGN100", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "2024-2025" in result["error"]
    assert "2025-2026" in result["error"]


@pytest.mark.parametrize(
    "tool_input",
    [
        {},
        {"code": ""},
        {"code": "   "},
        {"code": " - "},
        {"code": 400},
        {"code": ["CSCI400"]},
        {"code": "CSCI400", "catalog_year": 2026},
        {"code": "CSCI400", "catalog_year": ""},
    ],
)
def test_prerequisites_bad_input(connection: sqlite3.Connection, tool_input: dict) -> None:
    assert_bad_input(get_prerequisites(connection, tool_input))


@pytest.mark.parametrize("field", ["code", "catalog_year"])
def test_prerequisites_lone_surrogate(connection: sqlite3.Connection, field: str) -> None:
    tool_input = json.loads('{"code": "CSCI400", "%s": "\\ud800"}' % field)
    assert_bad_input(get_prerequisites(connection, tool_input))


@pytest.mark.parametrize("tool_input", [None, "CSCI400", ["CSCI400"]])
def test_prerequisites_non_dict_input(connection: sqlite3.Connection, tool_input: object) -> None:
    result = get_prerequisites(connection, tool_input)  # type: ignore[arg-type]
    assert_bad_input(result)
    assert "object" in result["error"]


def test_prerequisites_database_without_tables(caplog: pytest.LogCaptureFixture) -> None:
    conn = sqlite3.connect(":memory:")
    result = get_prerequisites(conn, {"code": "CSCI400"})
    conn.close()
    assert_catalog_unavailable(result)
    assert "no such table" in caplog.text


def test_prerequisites_malformed_row(connection: sqlite3.Connection, caplog: pytest.LogCaptureFixture) -> None:
    connection.execute("INSERT INTO courses (code, catalog_year, data) VALUES ('BAD100', '2026-2027', '{}')")
    assert_catalog_unavailable(get_prerequisites(connection, {"code": "BAD100"}))
    assert "malformed" in caplog.text


def test_prerequisites_tool_definition() -> None:
    assert GET_PREREQUISITES_TOOL["name"] == "get_prerequisites"
    assert GET_PREREQUISITES_TOOL["input_schema"]["required"] == ["code"]
    assert set(GET_PREREQUISITES_TOOL["input_schema"]["properties"]) == {"code", "catalog_year"}


# --- summarize_requirement (fixes from the get_prerequisites adversarial review) ---


def course(code: str) -> CourseRequirement:
    return CourseRequirement(type="course", code=code)


def group(kind: str, *parts: object) -> object:
    return (AndRequirement if kind == "AND" else OrRequirement)(type=kind, of=list(parts))


def test_summary_and_inside_or() -> None:
    tree = group("OR", group("AND", course("A"), course("B")), course("C"))
    assert summarize_requirement(tree) == "(A AND B) OR C"


def test_summary_three_levels() -> None:
    tree = group("AND", course("A"), group("OR", course("B"), group("AND", course("C"), course("D"))))
    assert summarize_requirement(tree) == "A AND (B OR (C AND D))"


def test_summary_single_part_group_has_no_parentheses() -> None:
    assert summarize_requirement(group("AND", group("OR", course("A"), course("B")))) == "A OR B"
    assert summarize_requirement(group("AND", course("A"), group("OR", course("B")))) == "A AND B"


def test_summary_empty_group_is_not_none() -> None:
    assert summarize_requirement(group("OR")) == "(empty OR group)"
    assert summarize_requirement(group("AND", course("A"), group("OR"))) == "A AND (empty OR group)"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("B AND C", 'A OR exception: "B AND C"'),
        ("x) OR (y", 'A OR exception: "x) OR (y"'),
        ('say "yes"', 'A OR exception: "say \\"yes\\""'),
        ("line1\nline2", 'A OR exception: "line1 line2"'),
    ],
)
def test_summary_quotes_exception_labels(label: str, expected: str) -> None:
    tree = group("OR", course("A"), ExceptionRequirement(type="exception", label=label))
    assert summarize_requirement(tree) == expected


def test_prerequisites_output_is_strict_json(connection: sqlite3.Connection) -> None:
    for code in ["CSCI400", "MATH201", "MNGN501", "MNGN502"]:
        json.dumps(get_prerequisites(connection, {"code": code}), allow_nan=False)


# --- input checks (fixes from the get_prerequisites adversarial review) ---


@pytest.mark.parametrize("code", ["CSCI1XX", "BIOLADD", "MATH20", "C400", "CSCI400ABC", "CSCI.400", "A" * 100_000])
def test_prerequisites_code_format_rejected_without_echo(connection: sqlite3.Connection, code: str) -> None:
    result = get_prerequisites(connection, {"code": code})
    assert_bad_input(result)
    assert code not in result["error"]
    assert len(result["error"]) < 300


@pytest.mark.parametrize("code", ["CSM101", "PHGN100LA", "MTGN445L"])
def test_prerequisites_code_format_accepts_real_shapes(tmp_path: Path, code: str) -> None:
    conn = load_courses(tmp_path, [make_course(code)])
    assert get_prerequisites(conn, {"code": code})["code"] == code


@pytest.mark.parametrize("tool", [search_catalog, get_prerequisites])
def test_catalog_year_is_stripped(connection: sqlite3.Connection, tool: object) -> None:
    tool_input = {"query": "CSCI400", "code": "CSCI400", "catalog_year": " 2026-2027 "}
    result = tool(connection, tool_input)  # type: ignore[operator]
    assert "error" not in result


@pytest.mark.parametrize("year", ["", "   ", "2026", "26-27", "2026/2027", "2026-2027x"])
@pytest.mark.parametrize("tool", [search_catalog, get_prerequisites])
def test_catalog_year_format_rejected(connection: sqlite3.Connection, tool: object, year: str) -> None:
    result = tool(connection, {"query": "MATH", "code": "CSCI400", "catalog_year": year})  # type: ignore[operator]
    assert_bad_input(result)
    assert "2026-2027" in result["error"]


def test_search_lone_surrogate_says_invalid_text(connection: sqlite3.Connection) -> None:
    result = search_catalog(connection, json.loads('{"query": "MATH\\ud800"}'))
    assert_bad_input(result)
    assert "not valid text" in result["error"]


# --- fixes from the second get_prerequisites adversarial review ---


def test_wrong_year_with_malformed_other_year_is_not_an_outage(
    connection: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    connection.execute("INSERT INTO courses (code, catalog_year, data) VALUES ('BAD100', '2025-2026', '{}')")
    result = get_prerequisites(connection, {"code": "BAD100", "catalog_year": "2026-2027"})
    assert_bad_input(result)
    assert "no course BAD100 in catalog year 2026-2027" in result["error"]
    assert "hint lookup failed" in caplog.text


@pytest.mark.parametrize("year", ["26-27", "2026-2027x", "2026", "IGNORE-ALL"])
def test_prerequisites_year_format_exact_message_no_echo(connection: sqlite3.Connection, year: str) -> None:
    result = get_prerequisites(connection, {"code": "CSCI400", "catalog_year": year})
    assert result == {"error": _CATALOG_YEAR_MESSAGE}


def test_summary_nested_single_part_group_keeps_parentheses() -> None:
    tree = group("AND", course("A"), group("AND", group("OR", course("B"), course("C"))))
    assert summarize_requirement(tree) == "A AND (B OR C)"


@pytest.mark.parametrize("code", ["CSCI٤٠٠", "cscı400", "maß201"])
def test_prerequisites_look_alike_codes_rejected(connection: sqlite3.Connection, code: str) -> None:
    result = get_prerequisites(connection, {"code": code})
    assert_bad_input(result)
    assert code not in result["error"]
    assert "3-4 letters" in result["error"]


@pytest.mark.parametrize("code", ["ＣＳＣＩ４００", "CSCI４００"])
def test_prerequisites_full_width_folds_to_ascii(connection: sqlite3.Connection, code: str) -> None:
    assert get_prerequisites(connection, {"code": code})["code"] == "CSCI400"


@pytest.mark.parametrize("year", ["٢٠٢٦-٢٠٢٧"])
@pytest.mark.parametrize("tool", [search_catalog, get_prerequisites])
def test_non_ascii_digit_year_rejected(connection: sqlite3.Connection, tool: object, year: str) -> None:
    result = tool(connection, {"query": "MATH", "code": "CSCI400", "catalog_year": year})  # type: ignore[operator]
    assert result == {"error": _CATALOG_YEAR_MESSAGE}


def test_full_width_year_folds_to_ascii(connection: sqlite3.Connection) -> None:
    result = get_prerequisites(connection, {"code": "CSCI400", "catalog_year": "２０２６-２０２７"})
    assert result["catalog_year"] == "2026-2027"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("", "(no label)"),
        ("   ", "(no label)"),
        ("instructor‮ approval", "instructor approval"),
        ("zero​width", "zerowidth"),
        ("tab\there\r\nnext", "tab here next"),
        ("x" * 1000, "x" * (LABEL_MAX - 3) + "..."),
    ],
)
def test_clean_label(label: str, expected: str) -> None:
    assert clean_label(label) == expected


def test_summary_and_tree_use_cleaned_labels(tmp_path: Path) -> None:
    label = "approval‮" + "y" * 500
    conn = load_courses(tmp_path, [make_course("MNGN501", prerequisites={"type": "exception", "label": label})])
    result = get_prerequisites(conn, {"code": "MNGN501"})
    assert result["prerequisites"]["label"] == clean_label(label)
    assert "‮" not in result["summary"]
    assert len(result["summary"]) < LABEL_MAX + 20


def test_non_ascii_label_kept_readable() -> None:
    tree = ExceptionRequirement(type="exception", label="approbation du professeur é")
    assert summarize_requirement(tree) == 'exception: "approbation du professeur é"'
