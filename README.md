# Assessment Skill Lab

Chat app that turns **20 approved SME assessments** into an authoring skill, then runs a **closed optimization loop**: generate → SME-compare → improve → **re-generate → re-compare → Δ verdict**. Each run improves the skill by one generation (v1 → v2 → …); `resume <run_id>` continues optimizing across runs until scores plateau.

## Closed loop

```
split ─ skill vN ─ generate 10 ─ compare vs holdout (baseline score)
                                        │
            improved skill vN+1 ◀─ improver agent
                    │
    re-generate 10 ─ re-compare vs SAME holdout ─ Δ verdict ✅/➖/❌
```

- **Baseline + improved scores** come from the SME comparator agent's rubric
  (house_style / structure / depth / clarity / completeness).
- **BLEU / embedding cosine** are topic-drift indicators only — not quality.
- Verdict uses a ±0.3 judge-noise threshold: `improved` / `within_noise` / `regressed`.

## How to run

### 1. Setup (once)

```bash
# clone, then create .env
cp .env.example .env      # set OPENROUTER_API_KEY (required)
                          # set GITHUB_TOKEN (optional, for downloading assessment repos)
```

**With uv (recommended):**
```bash
uv sync
```

**Without uv (plain venv + pip):**
```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install httpx chainlit sacrebleu
# macOS/Linux:
.venv/bin/python -m pip install httpx chainlit sacrebleu
```

Requires Python **3.13+**.

### 2. Start the app

```bash
# with uv:
uv run chainlit run app.py
# without uv (Windows):
.venv\Scripts\python -m chainlit run app.py
```

Open the printed URL (usually http://localhost:8000).

### 3. Provide 20 assessments

Either upload/paste directly in the UI (`.md` / `.txt` / `.json`, one per file,
`---` separators, or a JSON list) — or build the input set from GitHub repos:

```bash
# 1) edit the repo list in skill_lab/build_candidates.py, then:
.venv\Scripts\python -m skill_lab.build_candidates   # resolve branches -> candidates json
.venv\Scripts\python -m skill_lab.download_inputs    # download md from repo zips (in-memory)
.venv\Scripts\python -m skill_lab.finalize_inputs    # filter stubs, merge to exactly 20
```

This produces `data/skill_lab/inputs/assessments.json` — upload that single file in the UI.

### 4. Run and iterate

- Click **▶ Start closed loop** (or send `start`) — full run takes ~20–30 min.
- Read any document (skills, all generated assessments, reports) by clicking its
  name in chat; `docs` / **📖 Documents** re-opens the whole library.
- `runs` lists past runs with score history; `resume <run_id>` continues
  optimizing that run's improved skill on the same split.

## UI commands

| Command | Action |
|---|---|
| `start` | run the full closed loop on the 20 collected assessments |
| `resume <run_id>` | continue optimizing a previous run's improved skill |
| `runs` | list resumable runs with baseline/improved/Δ history |
| `docs` | re-open all documents of the current run |
| `reset` | clear the session |

## Project structure

```
Proto2/
├── app.py                     # Chainlit UI (closed loop, task tracker, doc library)
├── openrouter.py              # OpenRouter client (chat + embeddings) — sole LLM provider
├── chainlit.md                # in-app readme page
├── pyproject.toml / uv.lock   # dependencies (httpx, chainlit, sacrebleu)
├── .env.example               # template for .env (OPENROUTER_API_KEY, GITHUB_TOKEN)
├── public/                    # UI branding (custom.css, logo.svg)
├── .chainlit/config.toml      # Chainlit UI config (name, theme, layout)
│
├── skill_lab/                 # pipeline package
│   ├── models.py              #   Assessment / Split / SkillPackage dataclasses
│   ├── ingest.py              #   parse uploads/paste, require exactly 20
│   ├── split.py               #   seeded 10 train / 10 holdout split
│   ├── create_skill.py        #   train set -> seed skill package (LLM)
│   ├── generate.py            #   skill -> 10 assessments (LLM, progress callback)
│   ├── agent.py               #   generic OpenRouter tool-calling loop
│   ├── tools_aws.py           #   agent tools: assessments, structure checks, AWS snippets
│   ├── compare.py             #   SME comparator agent -> rubric report
│   ├── metrics.py             #   BLEU + embedding cosine (topic-drift indicators)
│   ├── improve.py             #   improver agent -> IMPROVER_SKILL.md -> improved skill
│   ├── pipeline.py            #   orchestration + verify() delta + cross-run resume
│   ├── store.py               #   run artifacts under data/skill_lab/runs/<run_id>/
│   ├── build_candidates.py    #   (input prep) repo list -> candidates json
│   ├── download_inputs.py     #   (input prep) repo zips -> markdown, in-memory
│   ├── finalize_inputs.py     #   (input prep) filter stubs, merge to 20
│   ├── download_aws_main.py   #   (legacy input prep; extracts to disk)
│   ├── e2e_test.py            #   end-to-end functional test
│   ├── smoke_agent.py         #   offline tool smoke test (+ optional live agent)
│   └── export_experiments_html.py
│
└── data/                      # gitignored — local only
    └── skill_lab/
        ├── inputs/            # prepared assessments (assessments.json, asm_XX.md)
        └── runs/<run_id>/     # per-run artifacts:
            ├── 01-assessments.json    02-split.json    manifest.json
            ├── 03-skill/              # skill vN (SKILL.md + references/)
            ├── 04-generated/          # 10 assessments from skill vN
            ├── 05-comparison/         # baseline report
            ├── 06-improver/           # IMPROVER_SKILL.md
            ├── 07-improved-skill/     # skill vN+1
            ├── 08-improved-generated/ # 10 assessments from skill vN+1
            ├── 09-improved-comparison/# improved report
            └── 10-verdict.json        # Δ scores + verdict
```

## What is local vs shared

**Commit / pull these:** `app.py`, `openrouter.py`, `skill_lab/`, `public/`, `.chainlit/config.toml`, `pyproject.toml`, `uv.lock`, `README.md`, `.env.example`, `chainlit.md`.

**Gitignored (stay on your machine only):** `.env` (secrets), `data/` (inputs + run artifacts), `.venv/`, `__pycache__/`, `.files/`, `*.log`.

## Tests

```bash
.venv\Scripts\python -m skill_lab.smoke_agent   # offline tools (+ tiny live agent if key set)
.venv\Scripts\python -m skill_lab.e2e_test      # full functional test (uses API credits)
```
