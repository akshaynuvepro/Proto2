# Proto2

Continuous improvement for AI agents from **real conversations**.

Proto2 learns from LangSmith SME chats and local coding-agent chats, turns them into **skill packages** + **daily reinforcement feedback**, then serves those artifacts to any MCP-capable agent.

---

## For agents (read this first)

If you are an AI agent connected to Proto2 MCPs, follow this contract.

### Your two MCPs

| MCP server | Direction | Your job with it |
|------------|-----------|------------------|
| `proto-capture` | **Write** conversations | Silently record the session (**any** agent/host) |
| `proto-skills` | **Read** skills + feedback | Load the right skill before answering domain tasks |

`proto-capture` is **agent-agnostic**: attach the MCP once; then record via `record_message` regardless of whether you are Cursor, Claude Code, Codex, Copilot, Windsurf, Gemini, or a custom host. Optional disk snapshots cover a few known CLIs; live tools work for everything.

Do **not** ask the user to call these tools. Do **not** narrate MCP calls unless asked.

### Required workflow every session

```text
1) SESSION START
   - proto-capture.record_conversations
   - proto-skills.get_feedback          # daily reinforcement rules
   - Follow feedback rules for the rest of the session

2) EACH USER MESSAGE (background)
   - proto-capture.record_message(role="user", text=..., agent=<your-host>)

3) BEFORE A DOMAIN / SANDBOX TASK
   - proto-skills.match_skill(query=<user request>)
   - proto-skills.get_skill(name=<top match>)
   - Obey SKILL.md over improvisation when they conflict
   - Optionally get_skill(..., include_references=true, include_scripts=true)
     if the skill points at references/scripts

4) EACH ASSISTANT REPLY (background)
   - proto-capture.record_message(role="assistant", text=..., agent=<your-host>)
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

## Integrate into another project (coding agents)

Use this when the target repo is **not** Proto2. Proto2 stays the skill/feedback source; the other project only **connects** to the MCPs.

### Minimum 5 steps

1. **Install CLIs once on the machine** (from the Proto2 checkout, not from the target repo):

```sh
cd /path/to/Proto2/capture && npm install && npm run install:local
cd /path/to/Proto2/skills-mcp && npm install && npm run install:local
proto-capture --version
proto-skills --version
```

2. **Point skills/feedback at the Proto2 data directory** (required when the agent cwd is another project):

```sh
# Windows PowerShell (user or session env)
setx PROTO_SKILLS_ROOT "C:\Users\<you>\Desktop\POCs\Proto2\data\skills"
setx PROTO_FEEDBACK_ROOT "C:\Users\<you>\Desktop\POCs\Proto2\data\langsmith\feedback"
# optional separate capture store for that project:
# setx PROTO_CAPTURE_STORE "C:\path\to\other-project\.proto-capture\conversations.json"
```

```sh
# macOS / Linux (shell profile or direnv)
export PROTO_SKILLS_ROOT="/path/to/Proto2/data/skills"
export PROTO_FEEDBACK_ROOT="/path/to/Proto2/data/langsmith/feedback"
# export PROTO_CAPTURE_STORE="/path/to/other-project/.proto-capture/conversations.json"
```

3. **Add MCP config only in the target project** (do not copy Proto2 source):

Cursor — create/update `<other-project>/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "proto-capture": {
      "command": "proto-capture",
      "args": ["mcp"]
    },
    "proto-skills": {
      "command": "proto-skills",
      "args": ["mcp"],
      "env": {
        "PROTO_SKILLS_ROOT": "C:/Users/<you>/Desktop/POCs/Proto2/data/skills",
        "PROTO_FEEDBACK_ROOT": "C:/Users/<you>/Desktop/POCs/Proto2/data/langsmith/feedback"
      }
    }
  }
}
```

Prefer putting the absolute Proto2 data paths in the MCP `env` block so the target project works even if global env vars are missing.

4. **Install silent skills (machine-wide)** so the agent auto-calls the MCPs:

```sh
proto-capture skill install --force
proto-skills skill install --force
```

5. **Verify from any directory**:

```sh
proto-skills doctor
proto-skills status
proto-skills match --query "recommend a US health plan for a diabetic member"
proto-capture status
```

In the target project’s agent chat: ask it to call `skills_status`, then `match_skill` + `get_skill` for a real request.

### What you should NOT do in the other project

- Do not vendor/copy `data/skills` unless you intentionally fork the skill corpus
- Do not run Proto2’s learning pipeline (`main.py extract/classify/skills`) unless you mean to operate Proto2 itself
- Do not hardcode relative `../Proto2/...` paths that break when the repo moves — use absolute paths in MCP `env`

### Cursor checklist for the other project

1. CLIs installed globally (`proto-capture`, `proto-skills` on `PATH`)
2. `<other-project>/.cursor/mcp.json` contains both servers
3. `PROTO_SKILLS_ROOT` / `PROTO_FEEDBACK_ROOT` set (MCP `env` or system env)
4. Cursor **Settings → MCP** shows both connected
5. Agent can call `skills_status` and gets `skillCount > 0`

### If `skillCount` is 0

Skills were not found. Fix paths:

```sh
proto-skills doctor
# skills root must contain catalog.json
dir "%PROTO_SKILLS_ROOT%\catalog.json"     # Windows
ls "$PROTO_SKILLS_ROOT/catalog.json"       # macOS/Linux
```

Rebuild catalog inside Proto2 if needed:

```sh
cd /path/to/Proto2
uv run python rebuild_catalog.py
```

---

## Human setup (one-time, Proto2 machine)

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

When using Proto2 itself as the workspace, defaults resolve to this repo’s `data/skills` and `data/langsmith/feedback` automatically. For **other** projects, set the env vars / MCP `env` as in [Integrate into another project](#integrate-into-another-project-coding-agents).

Reload the host MCP after install. Enable both servers in the host UI if needed.

### Install silent agent skills (recommended)

```sh
proto-capture skill install --force
proto-skills skill install --force
```

These teach assistants to call the MCPs automatically.

---

## MCP reference

### `proto-capture` — upload / record (any agent)

| Tool | Purpose |
|------|---------|
| `record_conversations` | Best-effort snapshot of known CLI stores (Claude / Codex / OpenCode / Gemini) |
| `record_message` | **Primary path** — append one live turn from **any** agent (`tool` / `agent` = free-form id) |
| `conversation_status` | Show store path, counts, last update |

Attach this MCP to any host. Live capture does not require Claude/Codex/etc. Disk snapshot is only a bonus for those CLIs. Optional Cursor hooks (`proto-capture hook …`) improve reliability without relying on the model.

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
| Skill catalog | `data/skills/catalog.json` (inside Proto2, or `$PROTO_SKILLS_ROOT/catalog.json`) |
| Skill packages | `data/skills/<slug>/SKILL.md` |
| Daily feedback | `data/langsmith/feedback/YYYY-MM-DD.md` (or `$PROTO_FEEDBACK_ROOT`) |

**Cross-project overrides (required outside Proto2 cwd):**

| Env | Meaning |
|-----|---------|
| `PROTO_SKILLS_ROOT` | Absolute path to Proto2 `data/skills` |
| `PROTO_FEEDBACK_ROOT` | Absolute path to Proto2 `data/langsmith/feedback` |
| `PROTO_CAPTURE_STORE` | Optional absolute path for that project’s conversation JSON |

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
| `skillCount` is 0 from another project | Set absolute `PROTO_SKILLS_ROOT` / MCP `env` to Proto2 `data/skills`; run `proto-skills doctor` |
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
