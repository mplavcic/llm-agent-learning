import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from base_specialist import (
    SUBMIT_RESULT_NAME,
    SpecialistResult,
    execute_with,
)
from specialists import REGISTRY
from specialists.technical import technical
from tests.test_agent import _tool_use_block, make_fake_client
from tools import get_tool

VALID = {
    "reasoning": "checked the purchase date against the policy",
    "evidence": ["purchased 2026-09-20", "today 2026-10-01"],
    "verdict": "resolved",
    "suggested_action": "hand off to a human for sign-off",
    "user_reply": "You are eligible for a refund.",
}


def submit(input_=VALID):
    return _tool_use_block("tu_submit", SUBMIT_RESULT_NAME, input_)


class TestSpecialistResult:
    def test_accepts_valid(self):
        assert SpecialistResult(**VALID).verdict == "resolved"

    def test_rejects_unknown_verdict(self):
        with pytest.raises(ValidationError):
            SpecialistResult(**{**VALID, "verdict": "maybe"})

    def test_requires_every_field(self):
        with pytest.raises(ValidationError):
            SpecialistResult(reasoning="x", verdict="resolved")


class TestScopedExecutor:
    def test_allows_listed_tool(self):
        execute = execute_with([get_tool("lookup_user")])
        _, is_error = execute("lookup_user", {"user_id": "u_004"})
        assert not is_error

    def test_rejects_unlisted_tool_before_it_runs(self):
        execute = execute_with([get_tool("lookup_user")])
        content, is_error = execute("get_purchases", {"user_id": "u_004"})
        assert is_error
        assert json.loads(content)["error"] == "tool_not_available"

    def test_technical_cannot_see_purchase_data(self):
        names = {schema["name"] for schema in technical.tool_schemas()}
        assert "lookup_user" in names
        assert "get_purchases" not in names


class TestRegistryInvariants:
    def test_every_specialist_can_submit_a_result(self):
        for specialist in REGISTRY.values():
            assert SUBMIT_RESULT_NAME in {s["name"] for s in specialist.tool_schemas()}

    def test_no_specialist_can_delegate(self):
        for specialist in REGISTRY.values():
            names = {s["name"] for s in specialist.tool_schemas()}
            assert "delegate_to_specialist" not in names

    def test_registry_keyed_by_specialist_name(self):
        assert all(name == specialist.name for name, specialist in REGISTRY.items())


class TestSpecialistLoop:
    def test_submit_result_terminates_the_loop(self):
        fake_create, captured = make_fake_client(
            [{"stop_reason": "tool_use", "tool_use": (submit(),)}]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            result = REGISTRY["refund"].run("refund?", "u_004")
        assert result.user_reply == VALID["user_reply"]
        assert len(captured) == 1

    def test_data_tool_runs_then_result_is_submitted(self):
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block(
                            "tu_1", "get_purchases", {"user_id": "u_004"}
                        ),
                    ),
                },
                {"stop_reason": "tool_use", "tool_use": (submit(),)},
            ]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run("refund?", "u_004")

        second_call = captured[1]
        assert [m["role"] for m in second_call] == ["user", "assistant", "user"]
        results = second_call[2]["content"]
        assert results[0]["type"] == "tool_result"
        assert results[0]["tool_use_id"] == "tu_1"
        assert not results[0]["is_error"]

    def test_user_id_prefixed_into_the_seed_message(self):
        fake_create, captured = make_fake_client(
            [{"stop_reason": "tool_use", "tool_use": (submit(),)}]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run("hello", "u_004")
        assert captured[0][0]["content"] == "[user_id: u_004]\n\nhello"

    def test_no_user_id_means_no_prefix(self):
        fake_create, captured = make_fake_client(
            [{"stop_reason": "tool_use", "tool_use": (submit(),)}]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            REGISTRY["refund"].run("hello")
        assert captured[0][0]["content"] == "hello"

    def test_end_turn_without_submit_is_loud(self):
        fake_create, _ = make_fake_client([{"stop_reason": "end_turn", "text": "hi"}])
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            with pytest.raises(RuntimeError, match="without calling submit_result"):
                REGISTRY["refund"].run("hello", "u_004")

    def test_invalid_submit_is_reported(self):
        bad = {**VALID, "verdict": "nonsense"}
        fake_create, _ = make_fake_client(
            [{"stop_reason": "tool_use", "tool_use": (submit(bad),)}]
        )
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            with pytest.raises(RuntimeError, match="invalid result"):
                REGISTRY["refund"].run("hello", "u_004")

    def test_iteration_guard(self):
        tool_call = {
            "stop_reason": "tool_use",
            "tool_use": (
                _tool_use_block("tu_1", "lookup_user", {"user_id": "u_004"}),
            ),
        }
        fake_create, _ = make_fake_client([tool_call] * 11)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            with pytest.raises(RuntimeError, match="did not finish"):
                REGISTRY["refund"].run("hello", "u_004")
