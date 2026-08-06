# Proto2

Continuous improvement for AI agents from **real conversations**.

Proto2 learns from LangSmith SME chats and local coding-agent chats, turns them into **skill packages** + **daily reinforcement feedback**, then serves those artifacts to any MCP-capable agent.

---

## For agents (read this first)

If you are an AI agent connected to Proto2 MCPs, follow this contract.

### Your two MCPs

| MCP server | Direction | Your job with it |
|------------|-----------|------------------|
| `proto-capture` | **Write** conversations | Silently record the session |
| `proto-skills` | **Read** skills + feedback | Load the right skill before answering domain tasks |

Do **not** ask the user to call these tools. Do **not** narrate MCP calls unless asked.

### Required workflow every session

```text
1) SESSION START
   - proto-capture.record_conversations
   - proto-skills.get_feedback          # daily reinforcement rules
   - Follow feedback rules for the rest of the session

2) EACH USER MESSAGE (background)
   - proto-capture.record_message(role="user", text=...)

3) BEFORE A DOMAIN / SANDBOX TASK
   - proto-skills.match_skill(query=<user request>)
   - proto-skills.get_skill(name=<top match>)
   - Obey SKILL.md over improvisation when they conflict
   - Optionally get_skill(..., include_references=true, include_scripts=true)
     if the skill points at references/scripts

4) EACH ASSISTANT REPLY (background)
   - proto-capture.record_message(role="assistant", text=...)
```

### Decision rules

1. **Always record.** Capture is local-only and silent.
2. **Always load feedback at session start** when `get_feedback` succeeds.
3. **Match then load.** Never invent a skill name; use `match_skill` first.
4. **If match score is weak / empty:** say you have no strong Proto2 skill, then proceed carefully without pretending one was loaded.
5. **Prefer skill + feedback constraints** (schemas, no markdown fences, completion checklists, grounding rules) over generic helpfulness.
6. **Never upload** conversation JSON or skill contents to external systems unless the user explicitly asks.

### Quick self-check tools

| Tool | Server | Use when |
|------|--------|----------|
| `conversation_status` | `proto-capture` | Verify recording path/count |
| `skills_status` | `proto-skills` | Verify catalog + feedback availability |
| `list_skills` | `proto-skills` | Browse available skills |

### Example (conceptual)

User: “Recommend a US health plan for a diabetic Texas member.”

1. `match_skill(query="Recommend a US health plan for a diabetic Texas member")`
2. Expect top hit like `medibuddy-health-plan-advisor`
3. `get_skill(name="medibuddy-health-plan-advisor")`
4. Execute that skill’s workflow and output contract exactly
5. Keep recording user/assistant turns via `proto-capture`

---

## Human setup (one-time)

### Install both CLIs

```sh
cd Proto2/capture
npm install
npm run install:local

cd ../skills-mcp
npm install
npm run install:local
```

Check:

```sh
proto-capture --version && proto-capture doctor
proto-skills --version && proto-skills doctor
```

### MCP config (any host)

```json
{
  "mcpServers": {
    "proto-capture": {
      "command": "proto-capture",
      "args": ["mcp"]
    },
    "proto-skills": {
      "command": "proto-skills",
      "args": ["mcp"]
    }
  }
}
```

This repo’s Cursor config is already set in [`.cursor/mcp.json`](.cursor/mcp.json).

Reload the host MCP after install. Enable both servers in the host UI if needed.

### Install silent agent skills (recommended)

```sh
proto-capture skill install --force
proto-skills skill install --force
```

These teach assistants to call the MCPs automatically.

---

## MCP reference

### `proto-capture` — upload / record

| Tool | Purpose |
|------|---------|
| `record_conversations` | Snapshot Claude / Codex / OpenCode / Gemini local stores into JSON |
| `record_message` | Append one live user/assistant/system turn |
| `conversation_status` | Show store path, counts, last update |

**Store locations**

| Mode | Path |
|------|------|
| Global install | `~/.proto-capture/conversations.json` |
| Dev (this repo) | `Proto2/data/capture/conversations.json` |
| Override | `PROTO_CAPTURE_STORE=<absolute-path>` |

On MCP connect, the server best-effort snapshots existing agent logs once. Nothing is uploaded.

Smoke:

```sh
proto-capture status
node capture/scripts/mcp-smoke.mjs
```

### `proto-skills` — consume skills + feedback

| Tool | Purpose |
|------|---------|
| `list_skills` | Catalog summary (name, description, triggers, tags) |
| `match_skill` | Rank skills for a query |
| `get_skill` | Load `SKILL.md` (+ optional references/scripts) |
| `get_feedback` | Daily reinforcement markdown (default: today, else latest) |
| `skills_status` | Skills/feedback paths and counts |

**Data locations**

| Artifact | Path |
|----------|------|
| Skill catalog | `data/skills/catalog.json` |
| Skill packages | `data/skills/<slug>/SKILL.md` |
| Daily feedback | `data/langsmith/feedback/YYYY-MM-DD.md` |

Overrides: `PROTO_SKILLS_ROOT`, `PROTO_FEEDBACK_ROOT`.

CLI helpers (no MCP needed):

```sh
proto-skills status
proto-skills list
proto-skills match --query "recommend a US health plan for a diabetic member"
proto-skills get --name medibuddy-health-plan-advisor
proto-skills feedback
```

---

## Host-specific notes

### Cursor

1. `npm run install:local` in `capture/` and `skills-mcp/`
2. [`.cursor/mcp.json`](.cursor/mcp.json) already lists both servers
3. **Settings → MCP** → enable `proto-capture` and `proto-skills` → reload if needed
4. Optional hooks: [`.cursor/hooks.json`](.cursor/hooks.json) (`proto-capture hook …`)
5. Install silent skills:

```sh
proto-capture skill install --force
proto-skills skill install --force
```

Verify by asking the agent to call `conversation_status` and `skills_status`.

### Claude Code

```sh
claude mcp add proto-capture -- proto-capture mcp
claude mcp add proto-skills -- proto-skills mcp
proto-capture skill install --claude --force
proto-skills skill install --claude --force
claude mcp list
```

### Codex CLI

```toml
[mcp_servers.proto-capture]
command = "proto-capture"
args = ["mcp"]

[mcp_servers.proto-skills]
command = "proto-skills"
args = ["mcp"]
```

```sh
proto-capture skill install --codex --force
proto-skills skill install --codex --force
```

### Gemini CLI / other hosts

Use the [generic MCP config](#mcp-config-any-host), then:

```sh
proto-capture skill install --force
proto-skills skill install --force
```

Checklist:

1. Both CLIs on `PATH` (`install:local`)
2. Both MCP servers configured with `args: ["mcp"]`
3. Host shows tools from both servers
4. Silent skills installed

Stdio MCP only (no remote HTTP deploy in these packages).

---

## Learning pipeline (produces what agents consume)

Humans/operators run this. Serving agents usually only **consume** via `proto-skills`.

### One-shot

```sh
# .env: LANGSMITH_API_KEY, OPENROUTER_API_KEY, optional ANALYSIS_MODEL
uv run python main.py --project main
# or stepwise:
uv run python main.py extract --source all
uv run python main.py classify
uv run python main.py skills
```

`--source langsmith|local|all` (default `all`). Local extract only reads the MCP capture store.

### Continuous worker

```sh
uv run python main.py worker --project main
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--interval` | `120` | Seconds between store polls |
| `--debounce` | `20` | Wait until store stops changing |
| `--langsmith-interval` | `900` | Seconds between LangSmith extracts |
| `--source` | `all` | `local` / `langsmith` / `all` |
| `--no-run-on-start` | off | Skip immediate first run |

Env overrides: `WORKER_INTERVAL`, `WORKER_DEBOUNCE`, `WORKER_LANGSMITH_INTERVAL`.

Each trigger runs extract → classify → skills with `--force`.

### What gets written for agents

```text
data/skills/catalog.json                 # router catalog
data/skills/<slug>/
  SKILL.md                               # operating instructions for that sandbox/domain
  references/                            # workflows / contracts
  scripts/                               # validators / helpers
data/langsmith/feedback/YYYY-MM-DD.md    # next-day reinforcement feedback
data/langsmith/conversations/...         # extracted session transcripts
```

Rebuild catalog only:

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

- Conversation JSON stays on disk (`PROTO_CAPTURE_STORE` or defaults above).
- Skills/feedback are local filesystem artifacts.
- No leaderboard / upload path in this project.
- The learning pipeline may send conversation bundles to OpenRouter for analysis when configured.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MCP not listed in Cursor | `install:local` both packages; enable both servers; reload window |
| `proto-capture` / `proto-skills` not found | Ensure Node is on `PATH`; re-run `npm run install:local` |
| Only one MCP appears | Add both blocks to host MCP config |
| Capture store empty | Install capture skill + Cursor hooks; confirm MCP connected |
| `match_skill` returns nothing useful | Rebuild catalog; check `proto-skills status` skillCount > 0 |
| `get_feedback` missing today | Normal if feedback not generated yet; tool falls back to latest date |
| OpenCode sessions missing | Use Node 22.13+ (SQLite) |
| Wrong paths | `proto-capture doctor` / `proto-skills doctor`; set env overrides |

```sh
proto-capture doctor
proto-capture status
proto-skills doctor
proto-skills status
```

---

## End-to-end verify

```sh
# Capture MCP
node capture/scripts/mcp-smoke.mjs
proto-capture status

# Skills MCP
proto-skills status
proto-skills match --query "UK energy REC MHHS flow"
proto-skills get --name utilityflow-uk-energy-rag
proto-skills feedback

# After chatting with a connected agent, materialize today's local MD
uv run python main.py extract --source local
```

Expected artifacts:

```text
data/capture/conversations.json
data/skills/catalog.json
data/skills/<slug>/SKILL.md
data/langsmith/feedback/YYYY-MM-DD.md
data/langsmith/conversations/.../*.md
```
