import sqlite3
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent.parent.parent / "degree_planner.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    code TEXT NOT NULL,
    catalog_year TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (code, catalog_year)
);

CREATE TABLE IF NOT EXISTS programs (
    program_id TEXT NOT NULL,
    catalog_year TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (program_id, catalog_year)
);

CREATE TABLE IF NOT EXISTS forms (
    form_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (form_id)
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (plan_id)
);
"""


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, with the schema ensured."""
    connection = get_connection()
    try:
        init_schema(connection)
        yield connection
    finally:
        connection.close()
