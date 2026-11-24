import json
import shutil
import sqlite3
from pathlib import Path

from degree_planner_backend.data_loader import refresh_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


def test_refresh_database_loads_valid_file(tmp_path: Path) -> None:
    _write(
        tmp_path / "math.json",
        {
            "courses": [
                {
                    "code": "MATH112",
                    "subject": "MATH",
                    "number": "112",
                    "title": "Calculus I",
                    "credits": 4.0,
                    "description": "",
                    "prerequisites": None,
                    "catalog_year": "2026-2027",
                }
            ]
        },
    )

    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)

    assert report.ok
    assert report.files_loaded == 1
    assert report.courses_loaded == 1
    row = connection.execute("SELECT code FROM courses").fetchone()
    assert row[0] == "MATH112"


def test_refresh_database_reports_error_per_file_without_aborting(tmp_path: Path) -> None:
    _write(tmp_path / "bad.json", {"courses": [{"code": "MATH112"}]})
    _write(
        tmp_path / "good.json",
        {
            "courses": [
                {
                    "code": "MATH223",
                    "subject": "MATH",
                    "number": "223",
                    "title": "Linear Algebra",
                    "credits": 3.0,
                    "description": "",
                    "prerequisites": None,
                    "catalog_year": "2026-2027",
                }
            ]
        },
    )

    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)

    assert not report.ok
    assert len(report.errors) == 1
    error_file = next(iter(report.errors))
    assert error_file.endswith("bad.json")
    # bad.json is still a valid JSON file, just with one bad course row (per-row validation), so
    # it still counts as loaded; its course is skipped and logged, not the whole file.
    assert report.files_loaded == 2
    assert report.courses_loaded == 1


def test_refresh_database_clears_stale_rows_on_reload(tmp_path: Path) -> None:
    path = tmp_path / "math.json"
    _write(
        path,
        {
            "courses": [
                {
                    "code": "MATH112",
                    "subject": "MATH",
                    "number": "112",
                    "title": "Calculus I",
                    "credits": 4.0,
                    "description": "",
                    "prerequisites": None,
                    "catalog_year": "2026-2027",
                }
            ]
        },
    )
    connection = sqlite3.connect(":memory:")
    refresh_database(tmp_path, connection)

    path.unlink()
    report = refresh_database(tmp_path, connection)

    assert report.ok
    assert report.courses_loaded == 0
    assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_refresh_database_loads_the_real_sample_file(tmp_path: Path) -> None:
    shutil.copy(REPO_ROOT / "docs" / "data-format.sample.json", tmp_path / "sample.json")

    connection = sqlite3.connect(":memory:")
    report = refresh_database(tmp_path, connection)

    assert report.ok
    assert report.courses_loaded == 7
    assert report.programs_loaded == 4
    assert report.forms_loaded == 1

    row = connection.execute("SELECT data FROM courses WHERE code = 'CSCI400'").fetchone()
    stored = json.loads(row[0])
    assert stored["prerequisites"]["type"] == "AND"
    assert stored["prerequisites"]["of"][1]["type"] == "OR"
    assert stored["corequisites"]["type"] == "OR"

    ranged = connection.execute("SELECT data FROM courses WHERE code = 'MNGN598'").fetchone()
    stored_ranged = json.loads(ranged[0])
    assert stored_ranged["credits_min"] == 1.0
    assert stored_ranged["credits_max"] == 6.0
