import json
from unittest.mock import patch

from tests.test_agent import _tool_use_block, make_fake_client
from tools import execute_tool, _BY_NAME


class TestPrepareCaseFile:
    def test_creates_case_file_with_evidence(self, tmp_path, monkeypatch):
        import artifacts

        cases = tmp_path / "case_files.jsonl"
        monkeypatch.setattr(artifacts, "CASE_FILES_PATH", cases)
        content, is_error = execute_tool(
            "prepare_case_file",
            {
                "case_type": "refund",
                "summary": "User wants refund",
                "evidence": ["Purchased 2026-09-20", "Today 2026-10-01"],
                "recommendation": "Check refund window",
                "user_id": "u_004",
            },
        )
        assert not is_error
        data = json.loads(content)
        assert data["case_id"].startswith("CF-")
        assert data["status"] == "created"

    def test_empty_evidence_is_error(self, tmp_path, monkeypatch):
        import artifacts

        cases = tmp_path / "case_files.jsonl"
        monkeypatch.setattr(artifacts, "CASE_FILES_PATH", cases)
        content, is_error = execute_tool(
            "prepare_case_file",
            {
                "case_type": "refund",
                "summary": "x",
                "evidence": [],
                "recommendation": "y",
                "user_id": "u_004",
            },
        )
        assert is_error
        assert "evidence" in json.loads(content)["error"]

    def test_invalid_case_type_error(self, tmp_path, monkeypatch):
        import artifacts

        cases = tmp_path / "case_files.jsonl"
        monkeypatch.setattr(artifacts, "CASE_FILES_PATH", cases)
        content, is_error = execute_tool(
            "prepare_case_file",
            {
                "case_type": "whatever",
                "summary": "x",
                "evidence": ["fact"],
                "recommendation": "y",
                "user_id": "u_004",
            },
        )
        assert is_error


class TestCreateSupportTicket:
    def test_creates_ticket(self, tmp_path, monkeypatch):
        import artifacts

        tickets = tmp_path / "tickets.jsonl"
        monkeypatch.setattr(artifacts, "TICKETS_PATH", tickets)
        content, is_error = execute_tool(
            "create_support_ticket",
            {
                "issue_type": "crash",
                "severity": "high",
                "description": "App crashes on launch",
                "steps_to_reproduce": ["Open app", "Tap login"],
                "evidence": ["Crash reported by user", "On Android"],
                "user_id": "u_004",
            },
        )
        assert not is_error
        data = json.loads(content)
        assert data["ticket_id"].startswith("YOC-")
        assert data["status"] == "open"

    def test_ticket_requires_evidence(self, tmp_path, monkeypatch):
        import artifacts

        tickets = tmp_path / "tickets.jsonl"
        monkeypatch.setattr(artifacts, "TICKETS_PATH", tickets)
        content, is_error = execute_tool(
            "create_support_ticket",
            {
                "issue_type": "bug",
                "severity": "medium",
                "description": "x",
                "steps_to_reproduce": ["do it"],
                "evidence": [],
                "user_id": "u_004",
            },
        )
        assert is_error
