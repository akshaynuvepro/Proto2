# Assessment Skill Lab

Chat app that turns **20 approved SME assessments** into a skill, generates assessments, compares them to a holdout set with an **agent-only SME comparator**, then builds an improvement skill and an improved skill.

## Flow

1. Paste or upload 20 assessments (markdown / text / JSON)
2. Split 10 train / 10 holdout
3. Create skill from train
4. Generate 10 assessments with that skill
5. SME comparator **agent** (tool use) vs holdout — then BLEU/embedding automatic metrics
6. Improvement **agent** (tool use) → apply improved skill package

Artifacts land in `data/skill_lab/runs/<run_id>/`.

## Compare & improve agents

`compare` and `improve` are not single-shot prompts. They run a small OpenRouter **tool-calling loop** (`skill_lab/agent.py`, max ~10 rounds) with local assessment + curated AWS tools (`skill_lab/tools_aws.py`):

| Tool | Purpose |
|------|---------|
| `list_assessments` | ids/titles for generated and/or holdout |
| `get_assessment` | full body by id |
| `get_skill_file` | read a path from the current skill package |
| `get_comparison_report` | prior report summary / priority_fixes (improve) |
| `get_improver_skill` | IMPROVER_SKILL.md (apply phase) |
| `run_structure_check` | heuristic duration/phases/resources/tutorial-tone |
| `lookup_aws_service` | offline curated snippets (S3, EKS, Lambda, IAM, …) |
| `search_aws_wellarchitected` | offline WA / assessment-craft snippets |
| `compute_text_overlap` | cheap BLEU between a gen/holdout pair |
| `fetch_aws_doc_hint` | optional httpx fetch of a public AWS docs path |

Reports keep the same JSON shape; `agent_trace` lists `{tool, ok}` calls. Automatic metrics (`automatic_metrics`) are still merged after the SME judge.

## Setup

```bash
cp .env.example .env   # set OPENROUTER_API_KEY (and optional GITHUB_TOKEN)
uv sync
uv run chainlit run app.py
```

Open the URL Chainlit prints (usually http://localhost:8000).

## Smoke test (tools + optional live agent)

```bash
uv run python -m skill_lab.smoke_agent
```

## What is local vs shared

**Commit / pull these:** `app.py`, `openrouter.py`, `skill_lab/`, `pyproject.toml`, `uv.lock`, `README.md`, `.env.example`, `chainlit.md`.

**Gitignored (stay on your machine only):**
- `.env` (secrets)
- `data/` — downloaded assessments, run artifacts, HTML/E2E reports under `data/skill_lab/`
- `.venv/`, `__pycache__/`, `.chainlit/`, `.files/`

Teammates regenerate runs locally after `uv sync` + their own `.env`. Optional: download AWS `_Main` assessments with `uv run python skill_lab/download_aws_main.py` when `GITHUB_TOKEN` is set.
