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
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticSerializationError

from degree_planner_backend.db import get_connection, init_schema
from degree_planner_backend.models import Course, Form, Program

ModelT = TypeVar("ModelT", bound=BaseModel)


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


def _validate_row(model: type[ModelT], raw: object, label: str) -> tuple[ModelT | None, str | None]:
    try:
        obj = model.model_validate(raw)
        # BUG-009: a course whose prerequisites nest too deep can parse here but then blow the
        # recursion limit (or fail to serialize at all) on every later read; reject it at load
        # instead of storing something every search will then trip over.
        model.model_validate_json(obj.model_dump_json())
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        return None, f"{label}: {messages}"
    except (RecursionError, PydanticSerializationError):
        return None, f"{label}: prerequisites are nested too deeply to be read back"
    return obj, None


def _parse_file(path: Path) -> tuple[dict | None, list[str]]:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]
    if not isinstance(raw, dict):
        return None, ["top level must be an object with courses/programs/forms"]
    return raw, []


def refresh_database(data_dir: Path, connection: sqlite3.Connection) -> LoadReport:
    report = LoadReport()
    init_schema(connection)
    connection.execute("DELETE FROM courses")
    connection.execute("DELETE FROM programs")
    connection.execute("DELETE FROM forms")

    # BUG-018: a form_id repeated across (or within) files silently replaces the earlier one; still
    # loaded (last one wins, as before), but now reported instead of hidden.
    seen_form_ids: dict[str, str] = {}

    for path in sorted(data_dir.rglob("*.json")):
        raw, errors = _parse_file(path)
        if errors:
            report.errors[str(path)] = errors
            continue
        assert raw is not None

        file_errors: list[str] = []
        file_catalog_year = raw.get("catalog_year") if isinstance(raw.get("catalog_year"), str) else None

        for index, item in enumerate(raw.get("courses") or []):
            course, error = _validate_row(Course, item, f"courses[{index}]")
            if error:
                file_errors.append(error)
                continue
            assert course is not None
            connection.execute(
                "INSERT OR REPLACE INTO courses (code, catalog_year, data) VALUES (?, ?, ?)",
                (course.code, course.catalog_year, course.model_dump_json()),
            )
            report.courses_loaded += 1

        for index, item in enumerate(raw.get("programs") or []):
            program, error = _validate_row(Program, item, f"programs[{index}]")
            if error:
                file_errors.append(error)
                continue
            assert program is not None
            connection.execute(
                "INSERT OR REPLACE INTO programs (program_id, catalog_year, data) VALUES (?, ?, ?)",
                (program.program_id, program.catalog_year, program.model_dump_json()),
            )
            report.programs_loaded += 1

        for index, item in enumerate(raw.get("forms") or []):
            # BUG-019: a form with no catalog_year of its own takes the file's.
            if file_catalog_year and isinstance(item, dict) and "catalog_year" not in item:
                item = {**item, "catalog_year": file_catalog_year}
            form, error = _validate_row(Form, item, f"forms[{index}]")
            if error:
                file_errors.append(error)
                continue
            assert form is not None
            if form.form_id in seen_form_ids:
                file_errors.append(
                    f"forms[{index}]: form_id {form.form_id!r} was already loaded from "
                    f"{seen_form_ids[form.form_id]}; this one replaces it"
                )
            seen_form_ids[form.form_id] = str(path)
            connection.execute(
                "INSERT OR REPLACE INTO forms (form_id, data) VALUES (?, ?)",
                (form.form_id, form.model_dump_json()),
            )
            report.forms_loaded += 1

        if file_errors:
            report.errors[str(path)] = file_errors
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
