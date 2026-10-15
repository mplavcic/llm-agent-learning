import json

from tools import TOOL_SCHEMAS, TOOL_SPECS, Tool, _BY_NAME, execute_tool


class TestExecuteTool:
    def test_lookup_user(self):
        content, is_error = execute_tool("lookup_user", {"user_id": "u_004"})
        assert not is_error
        assert json.loads(content)["name"] == "Priya"

    def test_user_not_found_is_error(self):
        content, is_error = execute_tool("lookup_user", {"user_id": "u_999"})
        assert is_error
        assert json.loads(content) == {"error": "user_not_found", "user_id": "u_999"}

    def test_get_purchases(self):
        content, is_error = execute_tool("get_purchases", {"user_id": "u_004"})
        assert not is_error
        data = json.loads(content)
        assert data["purchases"][0]["product"] == "Premium Counselling Plan"

    def test_get_today_date(self):
        content, is_error = execute_tool("get_today_date", {})
        assert not is_error
        assert "today" in json.loads(content)

    def test_search_kb_is_not_an_error_and_returns_results(self):
        content, is_error = execute_tool("search_kb", {"query": "refund policy"})
        assert not is_error
        results = json.loads(content)["results"]
        assert results[0]["id"] == "refund_policy"

    def test_search_kb_empty_result_is_not_an_error(self):
        content, is_error = execute_tool("search_kb", {"query": "zzzz"})
        assert not is_error
        assert json.loads(content) == {"results": []}

    def test_unknown_tool_is_error(self):
        content, is_error = execute_tool("nope", {})
        assert is_error
        assert json.loads(content)["error"] == "unknown_tool"

    def test_raising_tool_caught_by_safety_net(self, monkeypatch):
        def boom(user_id):
            raise RuntimeError("disk on fire")

        monkeypatch.setitem(
            _BY_NAME,
            "lookup_user",
            Tool(name="lookup_user", description="", input_schema={}, function=boom),
        )
        content, is_error = execute_tool("lookup_user", {"user_id": "u_004"})
        assert is_error
        assert json.loads(content) == {"error": "internal_tool_error", "name": "lookup_user"}

    def test_schema_shape(self):
        for spec in TOOL_SPECS:
            assert spec.name
            assert spec.description
            assert spec.input_schema["type"] == "object"
        assert {s["name"] for s in TOOL_SCHEMAS} == {s.name for s in TOOL_SPECS}