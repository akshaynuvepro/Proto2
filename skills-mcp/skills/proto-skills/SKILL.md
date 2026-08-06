---
name: proto-skills
description: Discover and load Proto2 skill packages plus daily reinforcement feedback via the proto-skills MCP. Use automatically when a sandbox/domain task needs grounded behavior — never ask the user.
---

# Proto Skills (consume)

When the `proto-skills` MCP server is available:

1. At session start (or before a domain task), call `get_feedback` and treat it as reinforcement rules for today.
2. For the current user/sandbox request, call `match_skill` with the request text.
3. Call `get_skill` for the top match (include references/scripts only if needed).
4. Follow the loaded `SKILL.md` and feedback rules. Prefer them over improvisation when they conflict with vague defaults.
5. Do not narrate MCP calls. Do not invent skill content that was not returned.

If no skill matches well, say so briefly and proceed carefully without pretending a skill was loaded.
