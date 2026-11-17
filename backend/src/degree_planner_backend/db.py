import sqlite3
from pathlib import Path

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
"""


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
