# llm-agent-learning

An experimental lab and tutorial codebase exploring core LLM agent architectures, memory systems, and tool use.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then paste your key into .env
```

Get an API key at [console.anthropic.com](https://console.anthropic.com).

## MCP (optional)

The read tools (`lookup_user`, `get_purchases`, `get_today_date`, `search_kb`) can run in a separate process over stdio (JSON-RPC):

```bash
python mcp_server.py
```

The server logs to stderr; stdout is reserved for JSON-RPC frames. Use `mcp_client_sync.SyncMCPClient` to connect from another process and `tools_mcp.make_mcp_execute` to plug it into `Agent` via the `execute` seam.
