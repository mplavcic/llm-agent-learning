import json

from mcp_client_sync import SyncMCPClient


def test_server_exposes_read_tools_only():
    with SyncMCPClient() as client:
        tools = client.list_tools()
        names = {t["name"] for t in tools}
        assert names == {"lookup_user", "get_purchases", "get_today_date", "search_kb"}
        for tool in tools:
            assert tool["name"]
            assert tool["description"]
            assert isinstance(tool["input_schema"], dict)


def test_lookup_user_via_mcp():
    with SyncMCPClient() as client:
        content, is_error = client.call_tool("lookup_user", {"user_id": "u_004"})
        assert not is_error
        data = json.loads(content)
        assert data["name"] == "Priya"


def test_get_purchases_via_mcp():
    with SyncMCPClient() as client:
        content, is_error = client.call_tool("get_purchases", {"user_id": "u_004"})
        assert not is_error
        data = json.loads(content)
        assert data["purchases"][0]["product"] == "Premium Counselling Plan"


def test_get_today_date_via_mcp():
    with SyncMCPClient() as client:
        content, is_error = client.call_tool("get_today_date", {})
        assert not is_error
        assert "today" in json.loads(content)


def test_search_kb_via_mcp():
    with SyncMCPClient() as client:
        content, is_error = client.call_tool("search_kb", {"query": "refund policy"})
        assert not is_error
        assert json.loads(content)["results"][0]["id"] == "refund_policy"


def test_user_not_found_via_mcp():
    with SyncMCPClient() as client:
        content, is_error = client.call_tool("lookup_user", {"user_id": "u_999"})
        assert is_error
        assert json.loads(content) == {"error": "user_not_found", "user_id": "u_999"}
