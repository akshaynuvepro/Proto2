# Proto2

Continuous skill improvement from **LangSmith SME chats** and **local coding-agent chats**.

Local capture is an **MCP server** (`proto-capture`). After one-time setup, agents record conversations in the background — you do not call MCP tools by hand.

---

## Connect proto-capture to any AI agent

### Deploy MCP locally (recommended)

You do **not** need to point agents at this repo folder. Install the CLI once on the machine:

```sh
cd Proto2/capture
npm install
npm run install:local
```

That builds and installs a global `proto-capture` command. Check:

```sh
proto-capture --version
proto-capture doctor
```

### Generic MCP config (any host)

Any client that supports **MCP over stdio**:

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

No project paths. Reload the host’s MCP after `install:local`.

| MCP tool | Purpose |
|---|---|
| `record_conversations` | Snapshot Claude / Codex / OpenCode / Gemini local stores into JSON |
| `record_message` | Append one live user/assistant/system turn |
| `conversation_status` | Path, counts, last update |

**Store**

| Mode | Path |
|---|---|
| Global install | `~/.proto-capture/conversations.json` |
| Dev (running from this repo) | `Proto2/data/capture/conversations.json` |
| Override | `PROTO_CAPTURE_STORE=<absolute-path>` |

Nothing is uploaded. Recording is local-only.

**On connect:** the server best-effort snapshots existing agent logs once.

Smoke-test without an agent:

```sh
proto-capture status
node capture/scripts/mcp-smoke.mjs
```

---

### Cursor

1. Run `npm run install:local` in `capture/` (above).
2. [`.cursor/mcp.json`](.cursor/mcp.json) already uses `"command": "proto-capture"`.
3. **Cursor Settings → MCP** → enable `proto-capture` → reload window if needed.
4. Optional: enable **Hooks** ([`.cursor/hooks.json`](.cursor/hooks.json) uses `proto-capture hook …`).
5. Install the silent-recording skill:

```sh
proto-capture skill install --force
```

**Verify:** ask the agent to call `conversation_status`.

---

### Claude Code

```sh
claude mcp add proto-capture -- proto-capture mcp
proto-capture skill install --claude --force
claude mcp list
```

---

### Codex CLI

```toml
[mcp_servers.proto-capture]
command = "proto-capture"
args = ["mcp"]
```

```sh
proto-capture skill install --codex --force
```

---

### Gemini CLI

Same MCP block as the [generic config](#generic-mcp-config-any-host), then:

```sh
proto-capture skill install --gemini --force
```

---

### Other agents (Windsurf, Continue, custom apps, etc.)

Use the [generic config](#generic-mcp-config-any-host). Checklist:

1. `npm run install:local` so `proto-capture` is on `PATH`
2. MCP: `command=proto-capture`, `args=["mcp"]`
3. Reload host → confirm three tools appear
4. `proto-capture skill install --force` for silent recording

Stdio MCP only (no remote HTTP deploy in this package).

---

### Background recording (so users never call MCP manually)

| Layer | What it does |
|---|---|
| **MCP on connect** | Auto-snapshots Claude/Codex/OpenCode/Gemini disk stores |
| **Agent Skill** | Mandates silent `record_conversations` / `record_message` every session |
| **Cursor hooks** | Records prompts/responses even if the model forgets tool calls |

Install skill for all supported assistants:

```sh
proto-capture skill install --force
```

---

### Verify end-to-end

```sh
# 1) MCP protocol + tools + store write
node capture/scripts/mcp-smoke.mjs

# 2) Store status
proto-capture status

# 3) After chatting with a connected agent, materialize today's local MD
uv run python main.py extract --source local
```

You should see files under:

```text
data/capture/conversations.json
data/langsmith/conversations/local/YYYY-MM-DD/*.md
```

---

## Learning pipeline (after capture)

### One-shot

```sh
# .env: LANGSMITH_API_KEY, OPENROUTER_API_KEY, optional ANALYSIS_MODEL
uv run python main.py --project main
# or stepwise:
uv run python main.py extract --source all
uv run python main.py classify
uv run python main.py skills
```

`--source langsmith|local|all` (default `all`). Local extract **only reads** the MCP store.

### Continuous worker

Keeps the analysis layer running: polls the local capture store for changes and periodically re-extracts LangSmith, then re-classifies and updates skills.

```sh
uv run python main.py worker --project main
```

| Flag | Default | Meaning |
|---|---|---|
| `--interval` | `120` | Seconds between store polls |
| `--debounce` | `20` | Wait until the store stops changing before running |
| `--langsmith-interval` | `900` | Seconds between LangSmith extracts |
| `--source` | `all` | `local` / `langsmith` / `all` |
| `--no-run-on-start` | off | Skip the immediate first run |

Env overrides: `WORKER_INTERVAL`, `WORKER_DEBOUNCE`, `WORKER_LANGSMITH_INTERVAL`.

On each trigger the worker runs extract → classify → skills with `--force` so growing sessions rewrite markdown and skills stay current. Errors are logged; the loop keeps running. Ctrl+C to stop.

### Skill packages & routing

```text
data/skills/catalog.json                 # agent router catalog
data/skills/<slug>/
  SKILL.md                               # description + triggers + tags + tools
  references/                            # mermaid workflows, output contracts
  scripts/                               # validators / helpers
  analysis-skill/SKILL.md
```

How a serving agent should pick a skill:

1. Load `data/skills/catalog.json`
2. Match the sandbox request to **description / triggers / tags**
3. Open that skill’s `SKILL.md`, then `references/` and `scripts/` as linked

```sh
uv run python rebuild_catalog.py
```

---

## Analysis UI

```sh
uv run python ui/server.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) for skills, classification, conversations, and capture store.

---

## Privacy

- Conversation JSON stays on disk under Proto2 `data/` (or `PROTO_CAPTURE_STORE`).
- No leaderboard / upload path in this project.
- The daily pipeline may send conversation bundles to OpenRouter for analysis (same as before).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| MCP not listed in Cursor | Run `npm run install:local`; enable server in Settings → MCP; reload window |
| `proto-capture` not found | `cd capture && npm run install:local` (needs Node on PATH) |
| Tools missing | Confirm args are `["mcp"]`; check host MCP logs |
| Store empty after chatting | Install skill + (in Cursor) enable hooks; confirm MCP shows connected |
| OpenCode sessions missing | Use Node 22.13+ (SQLite) |
| Wrong store path | `proto-capture doctor`; set `PROTO_CAPTURE_STORE` if you need a custom file |

```sh
proto-capture doctor
proto-capture status
```
