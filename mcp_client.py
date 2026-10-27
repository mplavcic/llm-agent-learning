import asyncio
import json
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPClient:
    """Minimal stdio MCP client for the support-tools server."""

    def __init__(self, command: str = sys.executable, args: list[str] | None = None, cwd: str | None = None, env: dict[str, str] | None = None):
        self.command = command
        self.args = args or ["mcp_server.py"]
        import os
        self.cwd = cwd or os.path.dirname(os.path.abspath(__file__))
        self.env = env
        self._session: ClientSession | None = None
        self._streams = None
        self._stack = None

    async def start(self):
        server_params = StdioServerParameters(command=self.command, args=self.args, cwd=self.cwd, env=self.env)
        self._stack = AsyncExitStack()
        read_stream, write_stream = await self._stack.enter_async_context(stdio_client(server_params))
        self._session = ClientSession(read_stream, write_stream)
        await self._stack.enter_async_context(self._session)
        await self._session.initialize()
        return self

    async def list_tools(self) -> list[dict[str, Any]]:
        if self._session is None:
            raise RuntimeError("client not started")
        result = await self._session.list_tools()
        tools = []
        for tool in getattr(result, "tools", []) or []:
            schema = getattr(tool, "inputSchema", None) or {}
            tools.append({
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "input_schema": schema,
            })
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> tuple[str, bool]:
        if self._session is None:
            raise RuntimeError("client not started")
        result = await self._session.call_tool(name, arguments or {})
        # Unwrap MCP content blocks into JSON string to match execute_tool contract
        content_parts = []
        for block in getattr(result, "content", []) or []:
            if getattr(block, "type", None) == "text":
                content_parts.append(block.text)
            elif hasattr(block, "text"):
                content_parts.append(block.text)
            else:
                content_parts.append(json.dumps(getattr(block, "__dict__", {})))
        content = content_parts[0] if len(content_parts) == 1 else "\n".join(content_parts)
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "error" in parsed:
                return content, True
        except Exception:
            pass
        if getattr(result, "isError", False):
            return content if content else json.dumps({"error": "tool_error"}), True
        return content, False

    async def close(self):
        if self._stack is not None:
            await self._stack.aclose()
        self._session = None
        self._streams = None
        self._stack = None

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


# Python 3.10 compatibility
try:
    from contextlib import AsyncExitStack
except ImportError:
    class AsyncExitStack:
        def __init__(self):
            self._cm = []
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            for cm in reversed(self._cm):
                await cm.__aexit__(*args)
        async def enter_async_context(self, cm):
            result = await cm.__aenter__()
            self._cm.append(cm)
            return result
        async def aclose(self):
            await self.__aexit__(None, None, None)
