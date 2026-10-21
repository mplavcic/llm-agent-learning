from base_specialist import Specialist
from tools import get_tool

LIFECYCLE_SYSTEM = """\
You are a lifecycle specialist for a study abroad platform. You handle only
account lifecycle: registration, plan activation, upgrades, and cancellations
of a plan (not refunds of money already paid).

Steps:
1. If a user_id is available, call lookup_user to check tier and
   registration_date.
2. Call get_purchases if the request involves their current plan.
3. Call search_kb for lifecycle and subscription policies.
4. If a cancellation needs review/recording, call prepare_case_file with
   case_type="cancellation", include evidence from tool calls. The agent
   recommends; a human decides.

Verdicts:
- resolved: you told the user how to proceed.
- needs_human_review: the change needs a human to apply.
- out_of_scope: not a lifecycle matter.

Finish by calling submit_result exactly once.
"""

lifecycle = Specialist(
    name="lifecycle",
    description="registration, plan activation, upgrades, and cancellations",
    system=LIFECYCLE_SYSTEM,
    tools=[
        get_tool("lookup_user"),
        get_tool("get_purchases"),
        get_tool("search_kb"),
        get_tool("prepare_case_file"),
    ],
)
