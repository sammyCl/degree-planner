"""Overlapping requests must not fail: a connection made in one worker thread is used in another (db.py)."""

import threading

from degree_planner_backend.db import get_connection


def test_a_connection_can_be_used_from_another_thread() -> None:
    connection = get_connection()
    errors: list[Exception] = []

    def use() -> None:
        try:
            connection.execute("SELECT 1").fetchone()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=use)
    worker.start()
    worker.join()
    connection.close()
    assert errors == []
