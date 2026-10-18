from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent import Agent
from config import SUPPORT_SYSTEM_PROMPT


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, tool_name, tool_input):
    return SimpleNamespace(
        type="tool_use", id=id_, name=tool_name, input=tool_input
    )


def make_response(stop_reason="end_turn", tool_use_blocks=(), text=""):
    content = list(tool_use_blocks)
    if text:
        content.append(_text_block(text))
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def make_fake_client(specs):
    captured = []

    def fake_create(**kwargs):
        # Snapshot the list: callers pass a live reference they keep mutating.
        captured.append(list(kwargs["messages"]))
        step = specs.pop(0)
        return make_response(
            stop_reason=step.get("stop_reason", "end_turn"),
            tool_use_blocks=step.get("tool_use", ()),
            text=step.get("text", ""),
        )

    return fake_create, captured


SYSTEM = "You are a customer support agent."


class TestAgentLoop:
    def test_defaults_to_shared_support_prompt(self):
        assert Agent().system == SUPPORT_SYSTEM_PROMPT

    def test_end_turn_returns_text(self):
        fake_create, _ = make_fake_client([{"stop_reason": "end_turn", "text": "hi"}])
        agent = Agent(SYSTEM)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            assert agent.chat("hello") == "hi"

    def test_tool_use_appended_before_results_in_one_message(self):
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block("tu_1", "lookup_user", {"user_id": "u_004"}),
                        _tool_use_block("tu_2", "get_today_date", {}),
                    ),
                },
                {"stop_reason": "end_turn", "text": "Priya is premium."},
            ]
        )
        agent = Agent(SYSTEM)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            assert agent.chat("refund?") == "Priya is premium."

        user_msg, assistant_msg, results_msg = captured[1]
        assert user_msg["role"] == "user"
        assert assistant_msg["role"] == "assistant"
        assert [b.type for b in assistant_msg["content"]] == ["tool_use", "tool_use"]
        assert results_msg["role"] == "user"
        results = results_msg["content"]
        assert isinstance(results, list) and len(results) == 2
        assert {r["tool_use_id"] for r in results} == {"tu_1", "tu_2"}
        assert all(r["type"] == "tool_result" for r in results)

    def test_all_tool_results_in_single_user_message(self):
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block("tu_1", "lookup_user", {"user_id": "u_004"}),
                        _tool_use_block("tu_2", "get_purchases", {"user_id": "u_004"}),
                        _tool_use_block("tu_3", "get_today_date", {}),
                    ),
                },
                {"stop_reason": "end_turn", "text": "done"},
            ]
        )
        agent = Agent(SYSTEM)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            agent.chat("refund?")

        second_call = captured[1]
        assert [m["role"] for m in second_call] == ["user", "assistant", "user"]
        results = second_call[2]["content"]
        assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2", "tu_3"]

    def test_max_tokens_stops_loudly(self):
        fake_create, _ = make_fake_client([{"stop_reason": "max_tokens"}])
        agent = Agent(SYSTEM)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            with pytest.raises(RuntimeError, match="max_tokens"):
                agent.chat("hello")

    def test_iteration_guard_raises(self):
        fake_create, _ = make_fake_client(
            [{"stop_reason": "tool_use", "tool_use": (_tool_use_block("tu_1", "get_today_date", {}),)}]
            * 11
        )
        agent = Agent(SYSTEM)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            with pytest.raises(RuntimeError, match="did not finish"):
                agent.chat("hello")