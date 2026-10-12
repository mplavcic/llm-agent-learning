import datetime
import json
from dataclasses import dataclass
from typing import Callable

from users import get_purchases, lookup_user


class ToolError(Exception):
    """A business-level tool failure, returned to the model as observation."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    function: Callable[..., dict]


def _today() -> dict:
    return {"today": datetime.date.today().isoformat()}


TOOL_SPECS = [
    Tool(
        name="lookup_user",
        description=(
            "Look up a user's profile by user_id. Returns the user's name, "
            "email, tier (free / premium / enterprise), and registration_date. "
            "Use this first whenever a user_id is available, so you can tailor "
            "your response to their tier. If the user does not exist, returns "
            '{"error": "user_not_found", "user_id": ...}.'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique user ID, e.g. 'u_004'.",
                }
            },
            "required": ["user_id"],
        },
        function=lookup_user,
    ),
    Tool(
        name="get_purchases",
        description=(
            "Look up a user's purchases by user_id. Returns the list of "
            "products they purchased with the purchase date and amount in INR. "
            "Use after lookup_user when the user asks about refunds, billing, "
            "or anything involving their purchases. If the user does not "
            'exist, returns {"error": "user_not_found", "user_id": ...}.'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique user ID, e.g. 'u_004'.",
                }
            },
            "required": ["user_id"],
        },
        function=get_purchases,
    ),
    Tool(
        name="get_today_date",
        description=(
            "Returns today's date as YYYY-MM-DD. Use whenever you need to "
            "know the current date, such as checking refund windows or "
            "subscription periods."
        ),
        input_schema={"type": "object", "properties": {}},
        function=_today,
    ),
]

TOOL_SCHEMAS = [
    {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.input_schema,
    }
    for spec in TOOL_SPECS
]

_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def execute_tool(name: str, args: dict) -> tuple[str, bool]:
    spec = _BY_NAME.get(name)
    if spec is None:
        error = {"error": "unknown_tool", "name": name}
        return json.dumps(error), True
    try:
        result = spec.function(**args)
    except ToolError as exc:
        return json.dumps(str(exc)), True
    except Exception:
        return json.dumps({"error": "internal_tool_error", "name": name}), True
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result), True
    return json.dumps(result), False