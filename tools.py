import datetime
import json
from dataclasses import dataclass
from typing import Callable

from artifacts import ArtifactError, CaseFileStore, TicketStore
from knowledge import search_kb
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


def _prepare_case_file(
    case_type: str,
    summary: str,
    evidence: list[str],
    recommendation: str,
    user_id: str,
) -> dict:
    try:
        record = CaseFileStore().create(
            case_type=case_type,
            summary=summary,
            evidence=evidence,
            recommendation=recommendation,
            user_id=user_id,
        )
    except ArtifactError as exc:
        return {"error": str(exc)}
    return {
        "case_id": record.case_id,
        "case_type": record.case_type,
        "created_at": record.created_at,
        "user_id": record.user_id,
        "status": "created",
        "message": "Case file created for human review. Recommendation is not a decision.",
    }


def _create_support_ticket(
    issue_type: str,
    severity: str,
    description: str,
    steps_to_reproduce: list[str],
    evidence: list[str],
    user_id: str,
) -> dict:
    try:
        record = TicketStore().create(
            issue_type=issue_type,
            severity=severity,
            description=description,
            steps_to_reproduce=steps_to_reproduce,
            evidence=evidence,
            user_id=user_id,
        )
    except ArtifactError as exc:
        return {"error": str(exc)}
    return {
        "ticket_id": record.ticket_id,
        "issue_type": record.issue_type,
        "severity": record.severity,
        "status": record.status,
        "created_at": record.created_at,
        "user_id": record.user_id,
        "message": "Support ticket created for engineering triage.",
    }


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
    Tool(
        name="search_kb",
        description=(
            "Search the knowledge base for policies and help articles. Pass a "
            "short query such as 'refund policy' or 'cancellation'. Returns "
            '{"results": [...]} where each result has a title and text; if '
            'nothing matches it returns {"results": []}. Always search before '
            "stating a policy or rule so your answer uses the current text."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for, e.g. 'refund policy'.",
                }
            },
            "required": ["query"],
        },
        function=search_kb,
    ),
    Tool(
        name="prepare_case_file",
        description=(
            "Create an immutable, append-only case file for human review. The "
            "agent recommends; a human decides. The evidence array MUST contain "
            "at least one concrete fact extracted from a tool call. Do not call "
            "this speculatively — gather evidence first with lookup_user, "
            "get_purchases, get_today_date, or search_kb. Writes are persistent "
            "and recorded in the audit log."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "case_type": {
                    "type": "string",
                    "enum": ["refund", "counsellor", "cancellation"],
                    "description": "The type of case.",
                },
                "summary": {
                    "type": "string",
                    "description": "A concise summary of the situation.",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete facts extracted from tool calls.",
                },
                "recommendation": {
                    "type": "string",
                    "description": "Your suggestion for a human to act on (not a decision).",
                },
                "user_id": {
                    "type": "string",
                    "description": "The user this case file is for.",
                },
            },
            "required": [
                "case_type",
                "summary",
                "evidence",
                "recommendation",
                "user_id",
            ],
        },
        function=_prepare_case_file,
    ),
    Tool(
        name="create_support_ticket",
        description=(
            "Create an immutable, append-only support ticket for engineering "
            "triage. Requires concrete evidence. Only use for confirmed or "
            "strongly suspected bugs/crashes after collecting evidence with "
            "lookup_user or search_kb. Do not use this for refunds or money. "
            "Writes are persistent and recorded in the audit log."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "enum": ["crash", "bug", "platform_issue"],
                    "description": "The kind of technical issue.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Your best assessment of severity.",
                },
                "description": {
                    "type": "string",
                    "description": "What the user is seeing.",
                },
                "steps_to_reproduce": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Repro steps gathered or inferred.",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete facts extracted from tool calls.",
                },
                "user_id": {
                    "type": "string",
                    "description": "The user reporting the issue.",
                },
            },
            "required": [
                "issue_type",
                "severity",
                "description",
                "steps_to_reproduce",
                "evidence",
                "user_id",
            ],
        },
        function=_create_support_ticket,
    ),
]

def to_schema(spec: Tool) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.input_schema,
    }


TOOL_SCHEMAS = [to_schema(spec) for spec in TOOL_SPECS]

_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def get_tool(name: str) -> Tool:
    return _BY_NAME[name]


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