import json
import logging
import sys

from mcp.server import MCPServer

# stdout is reserved for JSON-RPC. Log everything to stderr.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("support-mcp")

from knowledge import search_kb as _search_kb
from users import get_purchases as _get_purchases
from users import lookup_user as _lookup_user
import datetime

mcp = MCPServer("support-tools")


@mcp.tool()
def lookup_user(user_id: str) -> str:
    """Look up a user's profile by user_id. Returns the user's name, email, tier (free / premium / enterprise), and registration_date. If the user does not exist, returns {"error": "user_not_found", "user_id": ...}."""
    try:
        result = _lookup_user(user_id)
        logger.info(f"lookup_user called for {user_id}")
        return json.dumps(result)
    except Exception as exc:
        logger.exception("lookup_user failed")
        return json.dumps({"error": "internal_tool_error", "name": "lookup_user"})


@mcp.tool()
def get_purchases(user_id: str) -> str:
    """Look up a user's purchases by user_id. Returns the list of products they purchased with the purchase date and amount in INR. If the user does not exist, returns {"error": "user_not_found", "user_id": ...}."""
    try:
        result = _get_purchases(user_id)
        logger.info(f"get_purchases called for {user_id}")
        return json.dumps(result)
    except Exception as exc:
        logger.exception("get_purchases failed")
        return json.dumps({"error": "internal_tool_error", "name": "get_purchases"})


@mcp.tool()
def get_today_date() -> str:
    """Returns today's date as YYYY-MM-DD. Use whenever you need to know the current date, such as checking refund windows or subscription periods."""
    try:
        result = {"today": datetime.date.today().isoformat()}
        logger.info("get_today_date called")
        return json.dumps(result)
    except Exception as exc:
        logger.exception("get_today_date failed")
        return json.dumps({"error": "internal_tool_error", "name": "get_today_date"})


@mcp.tool()
def search_kb(query: str) -> str:
    """Search the knowledge base for policies and help articles. Pass a short query such as 'refund policy' or 'cancellation'. Returns {"results": [...]} where each result has a title and text; if nothing matches it returns {"results": []}."""
    try:
        result = _search_kb(query)
        logger.info(f"search_kb called for query={query!r}")
        return json.dumps(result)
    except Exception as exc:
        logger.exception("search_kb failed")
        return json.dumps({"error": "internal_tool_error", "name": "search_kb"})


if __name__ == "__main__":
    mcp.run("stdio")

