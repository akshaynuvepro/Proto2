# proto-capture

Local MCP server that records coding-agent conversations for Proto2.

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
