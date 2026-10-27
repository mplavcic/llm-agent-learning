from typing import Callable

from mcp_client_sync import SyncMCPClient


def make_mcp_execute(client: SyncMCPClient) -> Callable[[str, dict], tuple[str, bool]]:
    """Wrap an MCP client so it matches the Agent.execute/tool dispatch contract."""
    def execute(name: str, args: dict) -> tuple[str, bool]:
        return client.call_tool(name, args)
    return execute
