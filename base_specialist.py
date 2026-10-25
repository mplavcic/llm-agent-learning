import json
from dataclasses import dataclass, field
from typing import Callable, Literal

import llm
from config import MAX_TOKENS, MODEL
from hooks import HookContext, HookRegistry, hooked
from pydantic import BaseModel, ValidationError
from tools import Tool, execute_tool, to_schema

MAX_ITERATIONS = 10

Verdict = Literal[
    "resolved",
    "needs_human_review",
    "delegate_to_other",
    "out_of_scope",
    "ineligible",
]

VERDICTS = (
    "resolved",
    "needs_human_review",
    "delegate_to_other",
    "out_of_scope",
    "ineligible",
)


class SpecialistResult(BaseModel):
    """The structured handoff a specialist returns to the orchestrator.

    `reasoning` comes first: the same chain-of-thought-before-commit trick
    from Part 2. `verdict` is the categorical signal the orchestrator
    branches on in Python — never free text.
    """

    reasoning: str
    evidence: list[str]
    verdict: Verdict
    suggested_action: str
    user_reply: str


SUBMIT_RESULT_NAME = "submit_result"

SUBMIT_RESULT_SCHEMA = {
    "name": SUBMIT_RESULT_NAME,
    "description": (
        "Submit your final structured result. Call this exactly once, as your "
        "last action, after any data lookups. Provide `reasoning` first, then "
        "your `verdict`, then the rest."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Your reasoning before committing to a verdict.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete facts gathered from tools, one per item.",
            },
            "verdict": {
                "type": "string",
                "enum": list(VERDICTS),
                "description": "resolved, needs_human_review, delegate_to_other, "
                "out_of_scope, or ineligible.",
            },
            "suggested_action": {
                "type": "string",
                "description": "What should happen next, operationally.",
            },
            "user_reply": {
                "type": "string",
                "description": "A user-facing reply the orchestrator can relay.",
            },
        },
        "required": [
            "reasoning",
            "evidence",
            "verdict",
            "suggested_action",
            "user_reply",
        ],
    },
}


def execute_with(specs: list[Tool]) -> Callable[[str, dict], tuple[str, bool]]:
    """A scoped executor: only the given tools are callable.

    This is the authz boundary. A specialist whose list omits get_purchases
    cannot call it, even if the model names it — the request is rejected
    before it reaches the real tool.
    """
    allowed = {spec.name for spec in specs}

    def execute(name: str, args: dict) -> tuple[str, bool]:
        if name not in allowed:
            error = {
                "error": "tool_not_available",
                "name": name,
                "allowed": sorted(allowed),
            }
            return json.dumps(error), True
        return execute_tool(name, args)

    return execute


@dataclass(frozen=True)
class Specialist:
    """One domain expert: a focused prompt, a scoped tool list, and a loop.

    run() is the Part 4 agent loop, wrapped to terminate on submit_result
    and return a SpecialistResult instead of free text.
    """

    name: str
    description: str
    system: str
    tools: list[Tool] = field(default_factory=list)
    model: str = MODEL
    max_tokens: int = MAX_TOKENS

    def tool_schemas(self) -> list[dict]:
        return [to_schema(spec) for spec in self.tools] + [SUBMIT_RESULT_SCHEMA]

    def run(
        self,
        query: str,
        user_id: str | None = None,
        *,
        hooks: HookRegistry | None = None,
        context: HookContext | None = None,
    ) -> SpecialistResult:
        content = f"[user_id: {user_id}]\n\n{query}" if user_id else query
        messages = [{"role": "user", "content": content}]
        tools = self.tool_schemas()
        execute = execute_with(self.tools)
        if hooks is not None and context is not None:
            # The same hook layer that guards the orchestrator guards every
            # specialist's inner reads and writes — one uniform tool surface.
            execute = hooked(execute, hooks, context)

        for _ in range(MAX_ITERATIONS):
            response = llm.ask(
                messages,
                system=self.system,
                tools=tools,
                temperature=0,
                max_tokens=self.max_tokens,
                model=self.model,
            )
            if response.stop_reason == "tool_use":
                submit = [
                    block
                    for block in llm.tool_uses(response)
                    if block.name == SUBMIT_RESULT_NAME
                ]
                if submit:
                    try:
                        return SpecialistResult(**submit[0].input)
                    except ValidationError as exc:
                        raise RuntimeError(
                            f"Specialist {self.name!r} submitted an invalid "
                            f"result: {exc}"
                        ) from exc
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in llm.tool_uses(response):
                    result, is_error = execute(block.name, block.input)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                            "is_error": is_error,
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue
            if response.stop_reason == "end_turn":
                raise RuntimeError(
                    f"Specialist {self.name!r} finished without calling "
                    f"{SUBMIT_RESULT_NAME}"
                )
            raise RuntimeError(
                f"Specialist {self.name!r} stopped unexpectedly: "
                f"stop_reason={response.stop_reason!r}"
            )
        raise RuntimeError(
            f"Specialist {self.name!r} did not finish within {MAX_ITERATIONS} "
            "iterations"
        )
