import uuid

from agent import Agent
from config import MAX_TOKENS, MODEL
from conversation import Conversation
from delegate_tool import DELEGATE_SCHEMA, make_dispatcher
from hooks import (
    HookContext,
    HookRegistry,
    build_default_registry,
    hooked,
    utc_now,
)
from specialists import REGISTRY as SPECIALIST_REGISTRY
from users import tier_for

ORCHESTRATOR_MODEL = MODEL

ORCHESTRATOR_SYSTEM_TEMPLATE = """\
You are the orchestrator for a study abroad platform's support team. You do
not answer questions yourself and you never call data tools. Your only job is
to route the user's request to the right specialist(s) with the
delegate_to_specialist tool, then compose one reply for the user.

Specialists:
{roster}

Rules:
- Delegate with delegate_to_specialist(specialist, query). Rewrite the user's
  request into a clear, standalone query for the specialist.
- A message may contain more than one concern. Emit one delegate_to_specialist
  call per concern in the same turn.
- Never invent facts. Base the reply only on the specialists' user_reply fields.
- If a specialist returns verdict "needs_human_review", tell the user a human
  will follow up. If "out_of_scope", say you cannot help with that part. If
  "ineligible", explain politely using the specialist's reply.
- Keep the final reply concise and empathetic.
"""


def _roster(registry: dict) -> str:
    return "\n".join(
        f"- {specialist.name}: {specialist.description}"
        for specialist in registry.values()
    )


def build_system_prompt(registry: dict) -> str:
    return ORCHESTRATOR_SYSTEM_TEMPLATE.format(roster=_roster(registry))


class Orchestrator(Conversation):
    """The Part 5 Conversation, but with exactly one tool: delegate.

    Role, context, cost, authz — all four reasons the orchestrator holds no
    data tools. It routes; specialists work. verdict is the join column
    between the specialists' LLM judgment and this object's Python control
    flow: needs_human_review lands in human_queue deterministically.
    """

    def __init__(
        self,
        user_id: str | None = None,
        *,
        model: str = ORCHESTRATOR_MODEL,
        max_tokens: int = MAX_TOKENS,
        registry: dict | None = None,
        system: str | None = None,
        hooks: HookRegistry | None = None,
        context: HookContext | None = None,
    ):
        self.registry = registry if registry is not None else SPECIALIST_REGISTRY
        self.human_queue: list = []
        self.verdicts: list[str] = []
        self.hooks = hooks if hooks is not None else build_default_registry()
        self.context = context if context is not None else HookContext(
            user_id=user_id,
            tier=tier_for(user_id),
            session_id=uuid.uuid4().hex,
        )
        self.started_at = utc_now()
        self._ended = False
        self.last_summary: dict | None = None

        execute = make_dispatcher(
            user_id,
            on_result=self._observe,
            registry=self.registry,
            hooks=self.hooks,
            context=self.context,
        )
        # Delegation is a tool call too: routing is gated and audited by the
        # same hook layer as every specialist's inner tools.
        execute = hooked(execute, self.hooks, self.context)
        agent = Agent(
            system=system if system is not None else build_system_prompt(self.registry),
            tools=[DELEGATE_SCHEMA],
            execute=execute,
            model=model,
            max_tokens=max_tokens,
        )
        super().__init__(agent=agent, user_id=user_id)

    def _observe(self, result) -> None:
        self.verdicts.append(result.verdict)
        if result.verdict == "needs_human_review":
            self.human_queue.append(result)

    def end(self) -> dict:
        """Run Stop hooks once and return the session summary."""
        if self._ended and self.last_summary is not None:
            return self.last_summary
        self._ended = True
        summary = {
            "session_id": self.context.session_id,
            "user_id": self.context.user_id,
            "tier": self.context.tier,
            "turns": self.turn_count,
            "tool_calls": self.hooks.tool_calls,
            "denials": self.hooks.denials,
            "verdicts": list(self.verdicts),
            "human_queue_size": len(self.human_queue),
            "started_at": self.started_at,
            "ended_at": utc_now(),
        }
        self.last_summary = summary
        self.hooks.run_stop(summary)
        return summary
