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
    # check_same_thread=False: FastAPI may run get_db and the endpoint on different worker threads, and SQLite then
    # refused the connection ("objects created in a thread can only be used in that same thread"), a 500 whenever two
    # requests overlapped. Safe here: each request gets its own connection, never shared between requests.
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
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
