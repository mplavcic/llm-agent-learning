from unittest.mock import patch

from agent import Agent
from conversation import Conversation
from tests.test_agent import (
    _tool_use_block,
    make_fake_client,
)

SYSTEM = "You are a customer support agent."


def make_conversation(user_id=None):
    return Conversation(agent=Agent(SYSTEM), user_id=user_id)


class TestMemoryAcrossTurns:
    def test_second_turn_sends_full_history(self):
        fake_create, captured = make_fake_client(
            [
                {"stop_reason": "end_turn", "text": "turn one"},
                {"stop_reason": "end_turn", "text": "turn two"},
            ]
        )
        convo = make_conversation()
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("hello")
            convo.send("again")

        with_turn_2 = captured[1]
        assert [m["role"] for m in with_turn_2] == [
            "user",
            "assistant",
            "user",
        ]
        assert with_turn_2[0]["content"] == "hello"
        assert with_turn_2[1]["content"] == "turn one"
        assert with_turn_2[2]["content"] == "again"

    def test_tool_history_survives_into_next_turn(self):
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block("tu_1", "get_purchases", {"user_id": "u_004"}),
                    ),
                },
                {"stop_reason": "end_turn", "text": "you have 3 sessions left"},
                {"stop_reason": "end_turn", "text": "yes, cancel the rest"},
            ]
        )
        convo = make_conversation(user_id="u_004")
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("how many sessions left?")
            convo.send("cancel that then")

        # Turn 1 makes two API calls (tool_use, then final); turn 2's first
        # call is captured[2].
        with_turn_2 = captured[2]
        roles = [m["role"] for m in with_turn_2]
        assert roles == ["user", "assistant", "user", "assistant", "user"]
        results = with_turn_2[2]["content"]
        assert results[0]["type"] == "tool_result"
        assert results[0]["tool_use_id"] == "tu_1"
        assert with_turn_2[3]["content"] == "you have 3 sessions left"

    def test_no_pruning_of_tool_results(self):
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        _tool_use_block("tu_1", "get_purchases", {"user_id": "u_004"}),
                    ),
                },
                {"stop_reason": "end_turn", "text": "ok"},
                {"stop_reason": "end_turn", "text": "still ok"},
                {"stop_reason": "end_turn", "text": "and ok"},
            ]
        )
        convo = make_conversation(user_id="u_004")
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("one")
            convo.send("two")
            convo.send("three")

        tool_result_count = sum(
            1
            for m in convo.messages
            if isinstance(m["content"], list)
            and any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in m["content"]
            )
        )
        assert tool_result_count == 1

    def test_conversation_state_tracks_turns(self):
        fake_create, _ = make_fake_client(
            [
                {"stop_reason": "end_turn", "text": "a"},
                {"stop_reason": "end_turn", "text": "b"},
            ]
        )
        convo = make_conversation()
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("one")
            convo.send("two")

        assert convo.turn_count == 2
        # user, assistant, user, assistant — nothing dropped
        assert len(convo.messages) == 4


class TestUserIdInjection:
    def test_injected_only_on_first_turn(self):
        fake_create, captured = make_fake_client(
            [
                {"stop_reason": "end_turn", "text": "hi Priya"},
                {"stop_reason": "end_turn", "text": "sure"},
            ]
        )
        convo = make_conversation(user_id="u_004")
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("refund?")
            convo.send("thanks")

        assert captured[0][0]["content"] == "[user_id: u_004]\n\nrefund?"
        assert captured[1][2]["content"] == "thanks"
        assert sum("[user_id" in m["content"] for m in convo.messages if isinstance(m["content"], str)) == 1

    def test_no_user_id_attribute_no_injection(self):
        fake_create, captured = make_fake_client(
            [{"stop_reason": "end_turn", "text": "hi"}]
        )
        convo = make_conversation(user_id=None)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            convo.send("refund?")

        assert captured[0][0]["content"] == "refund?"


class TestSessionIsolation:
    def test_instances_do_not_share_messages(self):
        fake_create, _ = make_fake_client(
            [
                {"stop_reason": "end_turn", "text": "first session reply"},
                {"stop_reason": "end_turn", "text": "second session reply"},
            ]
        )
        alice = make_conversation(user_id="u_alice")
        bob = make_conversation(user_id="u_bob")
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            alice.send("hello from alice")
            bob.send("hello from bob")

        assert len(alice.messages) == 2
        assert len(bob.messages) == 2
        assert alice.messages[0]["content"] == "[user_id: u_alice]\n\nhello from alice"
        assert bob.messages[0]["content"] == "[user_id: u_bob]\n\nhello from bob"
        assert all(
            "alice" not in m["content"]
            for m in bob.messages
            if isinstance(m["content"], str)
        )
        assert all(
            "bob" not in m["content"]
            for m in alice.messages
            if isinstance(m["content"], str)
        )
