import json

import pytest

import hooks
from hooks import (
    BLOCKED_PREFIX,
    Deny,
    HookContext,
    HookEvent,
    HookRegistry,
    Modify,
    hooked,
)


def ctx(tier="premium", user_id="u_004", session_id="s_1"):
    return HookContext(user_id=user_id, tier=tier, session_id=session_id)


def event(name="lookup_user", args=None, **kw):
    return HookEvent(
        tool_name=name, tool_input=args or {"user_id": "u_004"}, context=ctx(**kw)
    )


def _audit_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestPreChain:
    def test_allow_continues_through_all_hooks(self):
        seen = []
        registry = HookRegistry(
            pre=[
                lambda e: seen.append("a"),
                lambda e: seen.append("b"),
            ]
        )
        assert registry.run_pre(event()) is None
        assert seen == ["a", "b"]

    def test_first_deny_wins_and_short_circuits(self):
        later = []
        registry = HookRegistry(
            pre=[
                lambda e: Deny("first"),
                lambda e: later.append("ran"),
            ]
        )
        decision = registry.run_pre(event())
        assert isinstance(decision, Deny)
        assert decision.reason == "first"
        assert later == []

    def test_modify_composes_into_next_hook(self):
        seen = []

        def second(e):
            seen.append(e.tool_input["user_id"])
            return None

        registry = HookRegistry(
            pre=[
                lambda e: Modify({"user_id": "u_017"}),
                second,
            ]
        )
        registry.run_pre(event())
        assert seen == ["u_017"]

    def test_pre_exception_propagates(self):
        def boom(e):
            raise RuntimeError("gate broken")

        registry = HookRegistry(pre=[boom])
        with pytest.raises(RuntimeError, match="gate broken"):
            registry.run_pre(event())


class TestPostChain:
    def test_post_receives_result(self):
        seen = []
        registry = HookRegistry(post=[lambda e, r: seen.append(r)])
        registry.run_post(event(), ('{"ok": true}', False))
        assert seen == [('{"ok": true}', False)]

    def test_post_failure_is_swallowed_and_recorded(self):
        def boom(e, r):
            raise RuntimeError("audit disk full")

        registry = HookRegistry(post=[boom])
        registry.run_post(event(), ("x", False))  # must not raise
        assert registry.post_failures == 1
        errors = _audit_lines(hooks.HOOK_ERRORS_PATH)
        assert len(errors) == 1
        assert errors[0]["hook_type"] == "PostToolUse"
        assert "audit disk full" in errors[0]["error"]


class TestStopChain:
    def test_stop_failure_is_swallowed_and_returned(self):
        def boom(summary):
            raise RuntimeError("cleanup failed")

        registry = HookRegistry(stop=[boom])
        failures = registry.run_stop({"session_id": "s_1"})
        assert len(failures) == 1
        assert _audit_lines(hooks.HOOK_ERRORS_PATH)[0]["hook_type"] == "Stop"


class TestHookedExecutor:
    def test_allow_runs_tool_and_counts(self):
        calls = []
        registry = HookRegistry()
        execute = hooked(
            lambda n, a: (calls.append((n, a)) or '{"ok": true}', False),
            registry,
            ctx(),
        )
        content, is_error = execute("lookup_user", {"user_id": "u_004"})
        assert calls == [("lookup_user", {"user_id": "u_004"})]
        assert not is_error
        assert registry.tool_calls == 1
        assert registry.denials == 0

    def test_deny_never_runs_tool_and_returns_blocked(self):
        calls = []
        registry = HookRegistry(pre=[lambda e: Deny("nope")])
        execute = hooked(
            lambda n, a: (calls.append(n) or "{}", False), registry, ctx()
        )
        content, is_error = execute("prepare_case_file", {"evidence": ["x"]})
        assert calls == []
        assert is_error
        assert json.loads(content)["message"].startswith(BLOCKED_PREFIX)
        assert registry.denials == 1
        assert registry.tool_calls == 0

    def test_blocked_attempt_is_audited(self):
        registry = HookRegistry(pre=[lambda e: Deny("tier")])
        execute = hooked(lambda n, a: ("{}", False), registry, ctx(tier="free"))
        execute("prepare_case_file", {"evidence": []})
        lines = _audit_lines(hooks.AUDIT_LOG_PATH)
        assert lines[0]["status"] == "blocked"
        assert lines[0]["tool"] == "prepare_case_file"
        assert lines[0]["reason"] == "tier"
        assert lines[0]["tier"] == "free"

    def test_modify_reaches_the_tool(self):
        registry = HookRegistry(pre=[lambda e: Modify({"user_id": "u_017"})])
        seen = {}
        execute = hooked(
            lambda n, a: (seen.update(a) or "{}", False), registry, ctx()
        )
        execute("lookup_user", {"user_id": "u_999"})
        assert seen["user_id"] == "u_017"
