# proto-capture

Local MCP server that records coding-agent conversations for Proto2.

**Agent-agnostic:** attach this MCP to any MCP-capable host and conversations can be captured. It does not depend on which agent product you use.

## How capture works (important)

MCP servers do not automatically see chat turns. Capture happens when the host/agent follows the server instructions and calls tools (or when optional host hooks fire).

| Path | Works with | What it does |
|------|------------|--------------|
| **Live MCP tools** (primary) | **Any** MCP host | Agent calls `record_message` each turn (instructed on connect) |
| **Disk snapshot** (bonus) | Claude Code / Codex / OpenCode / Gemini CLI | `record_conversations` / on-connect scrape of known local stores |
| **Host hooks** (optional) | Cursor (and similar) | `proto-capture hook …` appends without relying on the model |

Primary path for “any agent”: **attach MCP → agent silently calls `record_message`**.

## Deploy locally (recommended)

Install the CLI onto your machine once — agents then call `proto-capture`, not a project folder:

```sh
cd capture
npm run install:local
```

That builds and runs `npm install -g .`. Verify:

```sh
proto-capture --version
proto-capture doctor
```

### MCP config (any agent)

```json
{
  "mcpServers": {
    "proto-capture": {
      "command": "proto-capture",
      "args": ["mcp"]
    }
  }
}
```

No absolute paths to this repo. Reload the host’s MCP after install.

Optional (improves reliability on Claude/Codex/Gemini):

```sh
proto-capture skill install --force
```

### Store location

| Mode | Path |
|---|---|
| Global install (default) | `~/.proto-capture/conversations.json` |
| Running from Proto2 source tree | `Proto2/data/capture/conversations.json` |
| Override | `PROTO_CAPTURE_STORE=<absolute path>` |

Point Proto2’s pipeline at the same file if needed:

```sh
set PROTO_CAPTURE_STORE=%USERPROFILE%\.proto-capture\conversations.json
uv run python main.py extract --source local
```

### Uninstall

```sh
npm run uninstall:local
```

## Tools

| Tool | Purpose |
|------|---------|
| `record_conversations` | Session-start snapshot of known CLI stores (best-effort) |
| `record_message` | Append one live turn from **any** agent (`tool`/`agent` = free-form id) |
| `conversation_status` | Path + counts |

Example live call (any host):

```json
{
  "name": "record_message",
  "arguments": {
    "role": "user",
    "text": "…",
    "agent": "cursor"
  }
}
```
