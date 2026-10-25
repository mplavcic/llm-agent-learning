import json
from typing import Callable

from base_specialist import SpecialistResult
from hooks import HookContext, HookRegistry
from specialists import REGISTRY

DELEGATE_TOOL_NAME = "delegate_to_specialist"

DELEGATE_SCHEMA = {
    "name": DELEGATE_TOOL_NAME,
    "description": (
        "Delegate a single concern to a specialist. Rewrite the user's request "
        "into a clear standalone query. Emit one call per concern — if the "
        "message contains two concerns, emit two calls in the same turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "specialist": {
                "type": "string",
                "enum": sorted(REGISTRY),
                "description": "Which specialist should handle this concern.",
            },
            "query": {
                "type": "string",
                "description": "A standalone restatement of the concern.",
            },
        },
        "required": ["specialist", "query"],
    },
}


def make_dispatcher(
    user_id: str | None,
    *,
    on_result: Callable[[SpecialistResult], None] | None = None,
    registry: dict | None = None,
    hooks: HookRegistry | None = None,
    context: HookContext | None = None,
) -> Callable[[str, dict], tuple[str, bool]]:
    """Bind the delegate tool to one session's user_id.

    Delegation goes through the same tool_use path as every data tool, so the
    user_id never travels as model-authored text. Anything later that hooks
    tool_use (audit, gating) covers routing for free.
    """
    active = registry if registry is not None else REGISTRY

    def execute(name: str, args: dict) -> tuple[str, bool]:
        if name != DELEGATE_TOOL_NAME:
            return json.dumps({"error": "unknown_tool", "name": name}), True
        specialist_name = args.get("specialist")
        specialist = active.get(specialist_name)
        if specialist is None:
            error = {
                "error": "unknown_specialist",
                "specialist": specialist_name,
                "valid": sorted(active),
            }
            return json.dumps(error), True
        result = specialist.run(
            args.get("query", ""), user_id, hooks=hooks, context=context
        )
        if on_result is not None:
            on_result(result)
        return json.dumps(result.model_dump()), False

    return execute
