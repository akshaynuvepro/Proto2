# proto-skills

MCP server that lets agents **consume** Proto2 skills and daily reinforcement feedback.

Companion to `proto-capture` (which only records conversations).

## Install

```sh
cd skills-mcp
npm install
npm run install:local
```

Check:

```sh
proto-skills --version
proto-skills doctor
proto-skills status
```

## MCP config

```json
{
  "mcpServers": {
    "proto-skills": {
      "command": "proto-skills",
      "args": ["mcp"]
    }
  }
}
```

## Tools

| Tool | Purpose |
|------|---------|
| `list_skills` | Catalog summary |
| `match_skill` | Rank skills for a query |
| `get_skill` | Load `SKILL.md` (+ optional refs/scripts) |
| `get_feedback` | Daily reinforcement markdown |
| `skills_status` | Paths + counts |

## Env

| Var | Default |
|-----|---------|
| `PROTO_SKILLS_ROOT` | Proto2 `data/skills` when run from checkout; else `~/.proto-skills/skills` |
| `PROTO_FEEDBACK_ROOT` | Proto2 `data/langsmith/feedback` when from checkout; else `~/.proto-skills/feedback` |

## Agent skill install

```sh
proto-skills skill install --force
```
