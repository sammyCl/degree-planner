"""Loads and refreshes all collected catalog data (docs/data-format.md) into the database.

Scans a directory for `*.json` files holding any subset of courses/programs/forms,
validates each against the data format, and reports errors per file without letting
one bad file stop the rest from loading.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from degree_planner_backend.db import get_connection, init_schema
from degree_planner_backend.models import DataFile


@dataclass
class LoadReport:
    files_loaded: int = 0
    courses_loaded: int = 0
    programs_loaded: int = 0
    forms_loaded: int = 0
    errors: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_file(path: Path) -> tuple[DataFile | None, list[str]]:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]

    try:
        return DataFile.model_validate(raw), []
    except ValidationError as exc:
        errors = [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
        return None, errors


def refresh_database(data_dir: Path, connection: sqlite3.Connection) -> LoadReport:
    report = LoadReport()
    init_schema(connection)
    connection.execute("DELETE FROM courses")
    connection.execute("DELETE FROM programs")
    connection.execute("DELETE FROM forms")

    for path in sorted(data_dir.rglob("*.json")):
        data_file, errors = _parse_file(path)
        if errors:
            report.errors[str(path)] = errors
            continue

        assert data_file is not None
        for course in data_file.courses:
            connection.execute(
                "INSERT OR REPLACE INTO courses (code, catalog_year, data) VALUES (?, ?, ?)",
                (course.code, course.catalog_year, course.model_dump_json()),
            )
            report.courses_loaded += 1
        for program in data_file.programs:
            connection.execute(
                "INSERT OR REPLACE INTO programs (program_id, catalog_year, data) VALUES (?, ?, ?)",
                (program.program_id, program.catalog_year, program.model_dump_json()),
            )
            report.programs_loaded += 1
        for form in data_file.forms:
            connection.execute(
                "INSERT OR REPLACE INTO forms (form_id, data) VALUES (?, ?)",
                (form.form_id, form.model_dump_json()),
            )
            report.forms_loaded += 1
        report.files_loaded += 1

    connection.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load catalog data into the degree planner database")
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="data",
        help="directory to scan for data-format JSON files (default: data)",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"no such directory: {data_dir}", file=sys.stderr)
        return 1

    connection = get_connection()
    try:
        report = refresh_database(data_dir, connection)
    finally:
        connection.close()

    print(
        f"loaded {report.files_loaded} file(s): "
        f"{report.courses_loaded} course(s), {report.programs_loaded} program(s), {report.forms_loaded} form(s)"
    )
    for path, errors in report.errors.items():
        print(f"error in {path}:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
