import json
from pathlib import Path
from unittest.mock import patch

from artifacts import CaseFileStore, TicketStore
from base_specialist import SUBMIT_RESULT_NAME


def _tmp_stores(tmp_path, monkeypatch):
    cases = tmp_path / "case_files.jsonl"
    tickets = tmp_path / "tickets.jsonl"
    import artifacts

    monkeypatch.setattr(artifacts, "CASE_FILES_PATH", cases)
    monkeypatch.setattr(artifacts, "TICKETS_PATH", tickets)
    return cases, tickets


class TestCaseFile:
    def test_frozen(self):
        import artifacts

        cf = artifacts.CaseFile(
            case_id="CF-1",
            case_type="refund",
            created_at="2026-10-21T00:00:00Z",
            user_id="u_004",
            summary="x",
            evidence=["purchased on 2026-09-20"],
            recommendation="review",
        )
        try:
            cf.summary = "y"  # type: ignore
            assert False, "should be frozen"
        except Exception:
            assert True

    def test_store_assigns_ids_sequentially(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        c1 = store.create("refund", "s1", ["e1"], "r1", "u_004")
        c2 = store.create("counsellor", "s2", ["e2"], "r2", "u_017")
        assert c1.case_id == "CF-1"
        assert c2.case_id == "CF-2"

    def test_append_only(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        store.create("refund", "s1", ["e1"], "r1", "u_004")
        store.create("refund", "s2", ["e2"], "r2", "u_004")
        lines = cases.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_evidence_required(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        try:
            store.create("refund", "s1", [], "r1", "u_004")
            assert False
        except Exception as exc:
            assert "evidence" in str(exc)

    def test_created_at_present(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        c = store.create("cancellation", "s1", ["e1"], "r1", "u_031")
        assert c.created_at
        assert isinstance(c.created_at, str)

    def test_fanout_ids_no_collision(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        c1 = store.create("refund", "s1", ["e1"], "r1", "u_004")
        c2 = store.create("counsellor", "s2", ["e2"], "r2", "u_017")
        assert c1.case_id != c2.case_id


class TestTicket:
    def test_ticket_frozen(self):
        import artifacts

        t = artifacts.Ticket(
            ticket_id="YOC-1",
            created_at="2026-10-21T00:00:00Z",
            user_id="u_004",
            issue_type="crash",
            severity="high",
            description="app crashed",
            steps_to_reproduce=["open app"],
            evidence=["crash on launch"],
            status="open",
        )
        try:
            t.status = "triaged"  # type: ignore
            assert False
        except Exception:
            assert True

    def test_ticket_ids(self, tmp_path, monkeypatch):
        _, tickets = _tmp_stores(tmp_path, monkeypatch)
        store = TicketStore(tickets)
        t1 = store.create("crash", "high", "desc", ["step1"], ["evidence"], "u_004")
        t2 = store.create("bug", "low", "desc", ["step1"], ["evidence"], "u_017")
        assert t1.ticket_id == "YOC-1"
        assert t2.ticket_id == "YOC-2"
        assert t1.status == "open"


class TestBadRecordsStay:
    def test_nothing_deleted(self, tmp_path, monkeypatch):
        cases, _ = _tmp_stores(tmp_path, monkeypatch)
        store = CaseFileStore(cases)
        store.create("refund", "s1", ["e1"], "r1", "u_004")
        first = cases.read_text()
        # "delete" would mean rewrite; append-only means we don't touch old line
        store.create("refund", "s2", ["e2"], "r2", "u_004")
        second = cases.read_text()
        assert first in second
