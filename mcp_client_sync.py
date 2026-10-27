import asyncio
import atexit
import threading
from queue import Queue

from mcp_client import MCPClient


class SyncMCPClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._client = None
        self._loop = None
        self._thread = None

    def __enter__(self):
        self._loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        self._client = MCPClient(*self.args, **self.kwargs)
        future = asyncio.run_coroutine_threadsafe(self._client.start(), self._loop)
        future.result(timeout=30)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._client and self._loop:
            try:
                future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                future.result(timeout=10)
            except Exception:
                pass
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

    def list_tools(self):
        future = asyncio.run_coroutine_threadsafe(self._client.list_tools(), self._loop)
        return future.result(timeout=30)

    def call_tool(self, name, arguments=None):
        future = asyncio.run_coroutine_threadsafe(self._client.call_tool(name, arguments or {}), self._loop)
        return future.result(timeout=30)
