"""Lookup functions over the loaded catalog data (docs/data-format.md).

The agent tools (search_catalog, get_prerequisites, get_program_requirements,
get_forms) wrap these.
"""

from __future__ import annotations

import sqlite3

from degree_planner_backend.models import Course, Form, Program, Requirement, RequirementGroup


class NotFoundError(LookupError):
    """No row matched the given id (and catalog year, if given)."""


class AmbiguousLookupError(LookupError):
    """More than one catalog year matches; the caller must pass catalog_year."""


def _resolve_catalog_year(
    connection: sqlite3.Connection, table: str, id_column: str, id_value: str, catalog_year: str | None
) -> str:
    if catalog_year is not None:
        return catalog_year
    rows = connection.execute(f"SELECT DISTINCT catalog_year FROM {table} WHERE {id_column} = ?", (id_value,)).fetchall()
    if not rows:
        raise NotFoundError(f"no {table} row for {id_column}={id_value!r}")
    if len(rows) > 1:
        years = sorted(row[0] for row in rows)
        raise AmbiguousLookupError(f"{id_value!r} exists in catalog years {years}; pass catalog_year to disambiguate")
    return rows[0][0]


def get_course(connection: sqlite3.Connection, code: str, catalog_year: str | None = None) -> Course:
    year = _resolve_catalog_year(connection, "courses", "code", code, catalog_year)
    row = connection.execute("SELECT data FROM courses WHERE code = ? AND catalog_year = ?", (code, year)).fetchone()
    if row is None:
        raise NotFoundError(f"no course {code!r} in catalog year {year!r}")
    return Course.model_validate_json(row[0])


def get_prerequisites(connection: sqlite3.Connection, code: str, catalog_year: str | None = None) -> Requirement | None:
    return get_course(connection, code, catalog_year).prerequisites


def get_program(connection: sqlite3.Connection, program_id: str, catalog_year: str | None = None) -> Program:
    year = _resolve_catalog_year(connection, "programs", "program_id", program_id, catalog_year)
    row = connection.execute(
        "SELECT data FROM programs WHERE program_id = ? AND catalog_year = ?", (program_id, year)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no program {program_id!r} in catalog year {year!r}")
    return Program.model_validate_json(row[0])


def get_program_requirements(
    connection: sqlite3.Connection, program_id: str, catalog_year: str | None = None
) -> list[RequirementGroup]:
    return get_program(connection, program_id, catalog_year).requirement_groups


def search_catalog(connection: sqlite3.Connection, query: str, catalog_year: str | None = None, limit: int = 20) -> list[Course]:
    """Case-insensitive search over course code and title, optionally restricted to a catalog year."""
    sql = "SELECT data FROM courses"
    params: list[str] = []
    if catalog_year is not None:
        sql += " WHERE catalog_year = ?"
        params.append(catalog_year)
    courses = [Course.model_validate_json(row[0]) for row in connection.execute(sql, params).fetchall()]

    needle = query.strip().lower()
    matches = [course for course in courses if needle in course.code.lower() or needle in course.title.lower()]
    matches.sort(key=lambda course: course.code)
    return matches[:limit]


def get_forms(connection: sqlite3.Connection, program_id: str | None = None) -> list[Form]:
    """Forms and policies, optionally restricted to ones that apply to a program (or to any program)."""
    forms = [Form.model_validate_json(row[0]) for row in connection.execute("SELECT data FROM forms").fetchall()]
    if program_id is None:
        return forms
    return [form for form in forms if program_id in form.applies_to or "any" in form.applies_to]
