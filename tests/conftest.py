import pytest

import artifacts
import hooks


@pytest.fixture(autouse=True)
def _isolate_artifacts(tmp_path, monkeypatch):
    """Keep every test's JSONL writes inside its tmp dir, never the repo."""
    data = tmp_path / "data"
    monkeypatch.setattr(hooks, "AUDIT_LOG_PATH", data / "audit_log.jsonl")
    monkeypatch.setattr(hooks, "SESSION_SUMMARIES_PATH", data / "session_summaries.jsonl")
    monkeypatch.setattr(hooks, "HOOK_ERRORS_PATH", data / "hook_errors.jsonl")
    monkeypatch.setattr(artifacts, "CASE_FILES_PATH", data / "case_files.jsonl")
    monkeypatch.setattr(artifacts, "TICKETS_PATH", data / "tickets.jsonl")
