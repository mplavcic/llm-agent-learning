import json
from unittest.mock import patch

from base_specialist import SpecialistResult
from delegate_tool import DELEGATE_TOOL_NAME, make_dispatcher
from orchestrator import Orchestrator, build_system_prompt
from tests.test_agent import _tool_use_block, make_fake_client


def make_result(verdict="resolved", user_reply="done"):
    return SpecialistResult(
        reasoning="looked at the facts",
        evidence=["fact one"],
        verdict=verdict,
        suggested_action="proceed",
        user_reply=user_reply,
    )


class StubSpecialist:
    def __init__(self, name, result=None):
        self.name = name
        self.description = f"handles {name} things"
        self.result = result if result is not None else make_result()
        self.calls: list[tuple[str, str | None]] = []

    def run(self, query, user_id=None):
        self.calls.append((query, user_id))
        return self.result


def stub_registry():
    return {
        "refund": StubSpecialist("refund"),
        "counselling": StubSpecialist("counselling"),
    }


def delegate(id_, specialist, query):
    return _tool_use_block(
        id_, DELEGATE_TOOL_NAME, {"specialist": specialist, "query": query}
    )


class TestOrchestratorSurface:
    def test_exactly_one_tool(self):
        orchestrator = Orchestrator(user_id="u_004")
        assert [t["name"] for t in orchestrator.agent.tools] == [DELEGATE_TOOL_NAME]

    def test_system_prompt_lists_every_specialist(self):
        registry = stub_registry()
        prompt = build_system_prompt(registry)
        for name in registry:
            assert name in prompt


class TestDispatcher:
    def test_routes_to_the_named_specialist_with_user_id(self):
        registry = stub_registry()
        execute = make_dispatcher("u_004", registry=registry)
        content, is_error = execute(
            DELEGATE_TOOL_NAME, {"specialist": "refund", "query": "refund please"}
        )
        assert not is_error
        assert json.loads(content)["user_reply"] == "done"
        assert registry["refund"].calls == [("refund please", "u_004")]
        assert registry["counselling"].calls == []

    def test_unknown_specialist_is_an_error(self):
        execute = make_dispatcher("u_004", registry=stub_registry())
        content, is_error = execute(
            DELEGATE_TOOL_NAME, {"specialist": "legal", "query": "sue"}
        )
        assert is_error
        assert json.loads(content)["error"] == "unknown_specialist"

    def test_non_delegate_name_is_an_error(self):
        execute = make_dispatcher("u_004", registry=stub_registry())
        _, is_error = execute("lookup_user", {"user_id": "u_004"})
        assert is_error

    def test_verdict_observer_fires(self):
        seen = []
        registry = stub_registry()
        execute = make_dispatcher("u_004", on_result=seen.append, registry=registry)
        execute(DELEGATE_TOOL_NAME, {"specialist": "refund", "query": "q"})
        assert [r.verdict for r in seen] == ["resolved"]


class TestVerdictGating:
    def test_needs_human_review_lands_in_human_queue(self):
        registry = stub_registry()
        registry["refund"] = StubSpecialist(
            "refund", make_result("needs_human_review", "a human will review this")
        )
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (delegate("tu_1", "refund", "refund please"),),
                },
                {"stop_reason": "end_turn", "text": "A human will follow up."},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=registry)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            reply = orchestrator.send("refund please")

        assert reply == "A human will follow up."
        assert len(orchestrator.human_queue) == 1
        assert orchestrator.verdicts == ["needs_human_review"]

    def test_resolved_does_not_enqueue(self):
        fake_create, _ = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (delegate("tu_1", "refund", "refund please"),),
                },
                {"stop_reason": "end_turn", "text": "All set."},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=stub_registry())
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            orchestrator.send("refund please")

        assert orchestrator.human_queue == []
        assert orchestrator.verdicts == ["resolved"]


class TestFanOut:
    def test_two_concerns_run_both_specialists_in_one_turn(self):
        registry = stub_registry()
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (
                        delegate("tu_1", "counselling", "counsellor no-shows"),
                        delegate("tu_2", "refund", "refund the plan"),
                    ),
                },
                {"stop_reason": "end_turn", "text": "Here is what I found."},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=registry)
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            orchestrator.send("my counsellor never showed up and I want a refund")

        assert registry["counselling"].calls == [("counsellor no-shows", "u_004")]
        assert registry["refund"].calls == [("refund the plan", "u_004")]

        second_call = captured[1]
        results_msg = second_call[2]
        assert results_msg["role"] == "user"
        assert len(results_msg["content"]) == 2
        assert {r["tool_use_id"] for r in results_msg["content"]} == {"tu_1", "tu_2"}


class TestMemoryAndIsolation:
    def test_history_spans_turns(self):
        fake_create, captured = make_fake_client(
            [
                {
                    "stop_reason": "tool_use",
                    "tool_use": (delegate("tu_1", "refund", "refund please"),),
                },
                {"stop_reason": "end_turn", "text": "turn one"},
                {"stop_reason": "end_turn", "text": "turn two"},
            ]
        )
        orchestrator = Orchestrator(user_id="u_004", registry=stub_registry())
        with patch("llm.client") as client:
            client.return_value.messages.create = fake_create
            orchestrator.send("first")
            orchestrator.send("second")

        third_call = captured[2]
        assert third_call[0]["content"] == "[user_id: u_004]\n\nfirst"
        assert third_call[-1]["content"] == "second"
        assert len(third_call) >= 5

    def test_instances_do_not_share_state(self):
        alice = Orchestrator(user_id="u_alice", registry=stub_registry())
        bob = Orchestrator(user_id="u_bob", registry=stub_registry())
        alice.human_queue.append("x")
        assert bob.human_queue == []
        assert alice.messages is not bob.messages
        assert alice.verdicts is not bob.verdicts
