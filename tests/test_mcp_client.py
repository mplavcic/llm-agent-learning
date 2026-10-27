import json

from mcp_client_sync import SyncMCPClient
from tools_mcp import make_mcp_execute


def test_list_tools_matches_expected_shape():
    with SyncMCPClient() as client:
        tools = client.list_tools()
        by_name = {t["name"]: t for t in tools}
        assert "search_kb" in by_name
        assert isinstance(by_name["search_kb"]["input_schema"], dict)


def test_make_mcp_execute_bridge():
    with SyncMCPClient() as client:
        execute = make_mcp_execute(client)
        content, is_error = execute("lookup_user", {"user_id": "u_017"})
        assert not is_error
        assert json.loads(content)["name"] == "Daniel"


def test_subprocess_spawns_and_discovers_tools():
    with SyncMCPClient(args=["mcp_server.py"]) as client:
        tools = client.list_tools()
        assert len(tools) == 4
