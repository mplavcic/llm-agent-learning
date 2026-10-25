import json
from unittest.mock import patch

import artifacts
import hooks
from hooks import HookContext, build_default_registry
from orchestrator import Orchestrator
from specialists import REGISTRY
from tests.test_agent import _tool_use_block, make_fake_client
from tests.test_orchestrator import StubSpecialist, delegate, stub_registry


def _lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _submit(verdict="resolved"):
    return _tool_use_block(
        "tu_submit",
        "submit_result",
        {
            "reasoning": "r",
            "evidence": ["e"],
            "verdict": verdict,
            "suggested_action": "a",
            "user_reply": "ok",
        },
    )


class TestOrchestratorAudit:
    def test_delegation_is_audited(self):
        registry = stub_registry()
        registry["refund"] = StubSpecialist("refund")
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (delegate("tu_1", "refund", "refund please"),),
                },
                {"stop_reason": "end_turn", "text": "done"},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=registry)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            orchestrator.send("refund please")

        entries = _lines(hooks.AUDIT_LOG_PATH)
        assert [e["tool"] for e in entries] == ["delegate_to_specialist"]
        assert entries[0]["session_id"] == orchestrator.context.session_id
        assert entries[0]["status"] == "ok"

    def test_session_summary_written_once_on_end(self):
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (delegate("tu_1", "refund", "q"),),
                },
                {"stop_reason": "end_turn", "text": "done"},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=stub_registry())
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            orchestrator.send("q")
            first = orchestrator.end()
            second = orchestrator.end()

        rows = _lines(hooks.SESSION_SUMMARIES_PATH)
        assert len(rows) == 1
        assert first == second
        assert rows[0]["session_id"] == orchestrator.context.session_id
        assert rows[0]["turns"] == 1
        assert rows[0]["tool_calls"] == 1
        assert rows[0]["tier"] == "premium"


class TestSpecialistHooks:
    def test_free_tier_write_is_blocked_before_the_tool_runs(self):
        registry = build_default_registry()
        context = HookContext(user_id="u_017", tier="free", session_id="s_free")
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block(
                            "tu_1",
                            "prepare_case_file",
                            {
                                "case_type": "refund",
                                "summary": "x",
                                "evidence": ["purchase on 2026-01-05"],
                                "recommendation": "review",
                                "user_id": "u_017",
                            },
                        ),
                    ),
                },
                {"stop_reason": "tool_use", "tool_use": (_submit(),)},
            ]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run(
                "refund please", "u_017", hooks=registry, context=context
            )

        assert artifacts.CaseFileStore().list_all() == []
        tool_result = captured[1][2]["content"][0]
        assert tool_result["is_error"]
        assert json.loads(tool_result["content"])["message"].startswith(
            hooks.BLOCKED_PREFIX
        )
        blocked = [e for e in _lines(hooks.AUDIT_LOG_PATH) if e["status"] == "blocked"]
        assert blocked[0]["tool"] == "prepare_case_file"

    def test_premium_tier_write_executes_and_is_audited(self):
        registry = build_default_registry()
        context = HookContext(user_id="u_004", tier="premium", session_id="s_prem")
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block(
                            "tu_1",
                            "prepare_case_file",
                            {
                                "case_type": "refund",
                                "summary": "x",
                                "evidence": ["purchase on 2026-09-20"],
                                "recommendation": "review",
                                "user_id": "u_004",
                            },
                        ),
                    ),
                },
                {"stop_reason": "tool_use", "tool_use": (_submit(),)},
            ]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run(
                "refund please", "u_004", hooks=registry, context=context
            )

        cases = artifacts.CaseFileStore().list_all()
        assert len(cases) == 1
        entries = _lines(hooks.AUDIT_LOG_PATH)
        assert entries[0]["tool"] == "prepare_case_file"
        assert entries[0]["status"] == "ok"

    def test_mismatched_user_id_is_blocked(self):
        registry = build_default_registry()
        context = HookContext(user_id="u_004", tier="premium", session_id="s_mismatch")
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block(
                            "tu_1", "get_purchases", {"user_id": "u_017"}
                        ),
                    ),
                },
                {"stop_reason": "tool_use", "tool_use": (_submit(),)},
            ]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run(
                "refund please", "u_004", hooks=registry, context=context
            )

        tool_result = captured[1][2]["content"][0]
        assert tool_result["is_error"]
        assert "does not match" in json.loads(tool_result["content"])["message"]
