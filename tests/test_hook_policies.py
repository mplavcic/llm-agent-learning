from datetime import datetime

from hooks import (
    Deny,
    HookContext,
    HookEvent,
    build_default_registry,
    make_deploy_window_hook,
    tier_guard,
    user_id_guard,
)


def event(name, args=None, *, tier="premium", user_id="u_004"):
    return HookEvent(
        tool_name=name,
        tool_input=args if args is not None else {},
        context=HookContext(user_id=user_id, tier=tier, session_id="s_1"),
    )


class TestTierGuard:
    def test_free_user_cannot_create_case_file(self):
        decision = tier_guard(event("prepare_case_file", {"evidence": ["x"]}, tier="free"))
        assert isinstance(decision, Deny)
        assert "BLOCKED" not in decision.reason  # prefix added by the wrapper
        assert "free-tier" in decision.reason

    def test_free_user_can_file_a_support_ticket(self):
        assert tier_guard(event("create_support_ticket", {}, tier="free")) is None

    def test_free_user_reads_are_untouched(self):
        assert tier_guard(event("lookup_user", {}, tier="free")) is None

    def test_premium_and_enterprise_can_write(self):
        for tier in ("premium", "enterprise"):
            assert (
                tier_guard(event("prepare_case_file", {}, tier=tier)) is None
            )


class TestUserIdGuard:
    def test_mismatched_user_id_is_denied(self):
        decision = user_id_guard(
            event("lookup_user", {"user_id": "u_999"}, user_id="u_004")
        )
        assert isinstance(decision, Deny)
        assert "u_999" in decision.reason

    def test_matching_user_id_passes(self):
        assert user_id_guard(event("lookup_user", {"user_id": "u_004"})) is None

    def test_tools_without_user_id_pass(self):
        assert user_id_guard(event("search_kb", {"query": "refund"})) is None

    def test_no_session_user_means_no_comparison(self):
        assert (
            user_id_guard(event("lookup_user", {"user_id": "u_999"}, user_id=None))
            is None
        )


class TestDeployWindow:
    def _at(self, hour):
        return lambda: datetime(2026, 10, 25, hour, 0)

    def test_write_inside_window_is_denied(self):
        hook = make_deploy_window_hook(2, 4, now=self._at(3))
        decision = hook(event("prepare_case_file"))
        assert isinstance(decision, Deny)
        assert "deploy" in decision.reason

    def test_write_outside_window_passes(self):
        hook = make_deploy_window_hook(2, 4, now=self._at(9))
        assert hook(event("prepare_case_file")) is None

    def test_reads_are_never_blocked_by_the_window(self):
        hook = make_deploy_window_hook(2, 4, now=self._at(3))
        assert hook(event("lookup_user")) is None

    def test_overnight_window(self):
        hook = make_deploy_window_hook(23, 2, now=self._at(0))
        assert isinstance(hook(event("prepare_case_file")), Deny)
        hook = make_deploy_window_hook(23, 2, now=self._at(12))
        assert hook(event("prepare_case_file")) is None


class TestDefaultRegistry:
    def test_default_has_tier_and_user_guards(self, monkeypatch):
        monkeypatch.delenv("WRITE_FREEZE_START", raising=False)
        monkeypatch.delenv("WRITE_FREEZE_END", raising=False)
        registry = build_default_registry()
        names = [getattr(h, "__name__", "") for h in registry.pre]
        assert "user_id_guard" in names
        assert "tier_guard" in names

    def test_deploy_window_is_opt_in(self, monkeypatch):
        monkeypatch.setenv("WRITE_FREEZE_START", "2")
        monkeypatch.setenv("WRITE_FREEZE_END", "4")
        registry = build_default_registry()
        names = [getattr(h, "__name__", "") for h in registry.pre]
        assert "deploy_window_guard" in names

    def test_each_session_gets_fresh_counters(self):
        a = build_default_registry()
        b = build_default_registry()
        a.denials += 1
        assert b.denials == 0
