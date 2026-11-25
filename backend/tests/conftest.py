import pytest


@pytest.fixture(autouse=True)
def _agent_failure_log_in_tmp(tmp_path, monkeypatch):
    """Failed agent runs are logged to a file; keep the tests' ones out of the real backend/logs folder."""
    monkeypatch.setenv("DEGREE_PLANNER_LOG_DIR", str(tmp_path / "logs"))
