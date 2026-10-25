import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

AUDIT_LOG_PATH = Path("data/audit_log.jsonl")
SESSION_SUMMARIES_PATH = Path("data/session_summaries.jsonl")
HOOK_ERRORS_PATH = Path("data/hook_errors.jsonl")

WRITE_TOOLS = {"prepare_case_file", "create_support_ticket"}
FREE_TIER_BLOCKED_WRITES = {"prepare_case_file"}

BLOCKED_PREFIX = "BLOCKED: "


@dataclass(frozen=True)
class HookContext:
    """Trusted server-side session state. Never built from LLM output."""

    user_id: str | None
    tier: str
    session_id: str


@dataclass
class HookEvent:
    tool_name: str
    tool_input: dict
    context: HookContext


@dataclass(frozen=True)
class Deny:
    reason: str


@dataclass(frozen=True)
class Modify:
    tool_input: dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _log_hook_error(hook_type: str, hook, event, exc: Exception) -> None:
    record = {
        "ts": utc_now(),
        "hook_type": hook_type,
        "hook": getattr(hook, "__name__", repr(hook)),
        "tool": event.tool_name if event is not None else None,
        "session_id": event.context.session_id if event is not None else None,
        "error": f"{type(exc).__name__}: {exc}",
    }
    try:
        append_jsonl(HOOK_ERRORS_PATH, record)
    except Exception:
        pass
    try:
        print(f"hook failure ({hook_type}): {record['error']}", file=sys.stderr)
    except Exception:
        pass


class HookRegistry:
    """Ordered PreToolUse/PostToolUse/Stop hooks plus per-session counters."""

    def __init__(
        self,
        *,
        pre: list[Callable] | None = None,
        post: list[Callable] | None = None,
        stop: list[Callable] | None = None,
    ):
        self.pre = list(pre or [])
        self.post = list(post or [])
        self.stop = list(stop or [])
        self.tool_calls = 0
        self.denials = 0
        self.post_failures = 0

    def add_pre(self, hook: Callable) -> Callable:
        self.pre.append(hook)
        return hook

    def add_post(self, hook: Callable) -> Callable:
        self.post.append(hook)
        return hook

    def add_stop(self, hook: Callable) -> Callable:
        self.stop.append(hook)
        return hook

    def run_pre(self, event: HookEvent) -> Deny | None:
        for hook in self.pre:
            decision = hook(event)
            if isinstance(decision, Deny):
                return decision
            if isinstance(decision, Modify):
                event.tool_input = decision.tool_input
        return None

    def run_post(self, event: HookEvent, result: tuple[str, bool]) -> None:
        for hook in self.post:
            try:
                hook(event, result)
            except Exception as exc:
                self.post_failures += 1
                _log_hook_error("PostToolUse", hook, event, exc)

    def run_stop(self, summary: dict) -> list[Exception]:
        failures = []
        for hook in self.stop:
            try:
                hook(summary)
            except Exception as exc:
                failures.append(exc)
                _log_hook_error("Stop", hook, None, exc)
        return failures


def hooked(
    execute: Callable[[str, dict], tuple[str, bool]],
    registry: HookRegistry,
    context: HookContext,
) -> Callable[[str, dict], tuple[str, bool]]:
    """Wrap a tool executor with the hook lifecycle.

    A denial still returns a normal (content, is_error) tuple, so the agent
    loop can answer the tool_use with a matching tool_result — the API
    contract holds and the model recovers from the BLOCKED observation.
    """

    def run_tool(name: str, args: dict) -> tuple[str, bool]:
        event = HookEvent(tool_name=name, tool_input=dict(args), context=context)
        decision = registry.run_pre(event)
        if isinstance(decision, Deny):
            registry.denials += 1
            append_jsonl(
                AUDIT_LOG_PATH,
                {
                    "ts": utc_now(),
                    "status": "blocked",
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "tier": context.tier,
                    "tool": name,
                    "input": args,
                    "reason": decision.reason,
                },
            )
            message = {
                "error": "blocked",
                "message": f"{BLOCKED_PREFIX}{decision.reason}",
            }
            return json.dumps(message), True

        content, is_error = execute(name, event.tool_input)
        registry.tool_calls += 1
        registry.run_post(event, (content, is_error))
        return content, is_error

    return run_tool


def tier_guard(event: HookEvent) -> Deny | None:
    if event.context.tier == "free" and event.tool_name in FREE_TIER_BLOCKED_WRITES:
        return Deny(
            "free-tier users cannot call prepare_case_file. Suggest upgrading "
            "the plan or route the user to the general FAQ."
        )
    return None


def user_id_guard(event: HookEvent) -> Deny | None:
    claimed = event.tool_input.get("user_id")
    if claimed is None or event.context.user_id is None:
        return None
    if claimed != event.context.user_id:
        return Deny(
            f"user_id {claimed!r} does not match the session user "
            f"{event.context.user_id!r}. Never use a user_id other than the "
            "session user's."
        )
    return None


def make_deploy_window_hook(
    start_hour: int,
    end_hour: int,
    *,
    now: Callable[[], datetime] | None = None,
) -> Callable[[HookEvent], Deny | None]:
    clock = now if now is not None else datetime.now

    def deploy_window_guard(event: HookEvent) -> Deny | None:
        if event.tool_name not in WRITE_TOOLS:
            return None
        hour = clock().hour
        if start_hour <= end_hour:
            in_window = start_hour <= hour < end_hour
        else:
            in_window = hour >= start_hour or hour < end_hour
        if in_window:
            return Deny(
                f"writes are frozen between {start_hour:02d}:00 and "
                f"{end_hour:02d}:00 for the weekly deploy. Ask the user to "
                "try again after the window."
            )
        return None

    return deploy_window_guard


def audit_log(event: HookEvent, result: tuple[str, bool]) -> None:
    content, is_error = result
    append_jsonl(
        AUDIT_LOG_PATH,
        {
            "ts": utc_now(),
            "status": "error" if is_error else "ok",
            "session_id": event.context.session_id,
            "user_id": event.context.user_id,
            "tier": event.context.tier,
            "tool": event.tool_name,
            "input": event.tool_input,
            "result": content,
            "is_error": is_error,
        },
    )


def session_summary(summary: dict) -> None:
    append_jsonl(SESSION_SUMMARIES_PATH, summary)


def build_default_registry() -> HookRegistry:
    """A fresh registry per session, so counters never leak across users."""
    registry = HookRegistry(
        pre=[user_id_guard, tier_guard],
        post=[audit_log],
        stop=[session_summary],
    )
    start = os.environ.get("WRITE_FREEZE_START")
    end = os.environ.get("WRITE_FREEZE_END")
    if start not in (None, "") and end not in (None, ""):
        registry.add_pre(make_deploy_window_hook(int(start), int(end)))
    return registry
