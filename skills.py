"""Per-sandbox self-evolving SKILL.md + analysis_instructions.md store."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from analyze import FEEDBACK_SYSTEM_PROMPT, call_openrouter, extract_json_object
from extract import get_tz, yaml_escape

DEFAULT_ANALYSIS_INSTRUCTIONS = FEEDBACK_SYSTEM_PROMPT
REQUIRED_ANALYSIS_KEYS = (
    "title", "executive_summary", "mistakes", "user_hassle_hotspots",
    "knowledge_to_internalize", "behavior_rules_for_next_run",
    "prompt_additions", "prioritized_actions", "positive_patterns_to_keep",
)

MERGE_SKILL_SYSTEM_PROMPT = """You maintain ONE cumulative Agent Skill package for a single sandbox scenario.

A downstream agent discovers skills by reading frontmatter `description`, `triggers`, and `tags`.
It then opens SKILL.md + linked references/ + scripts/ to execute the sandbox correctly.

You will receive:
- the sandbox name
- CURRENT description / triggers / tags / tools (or empty if brand-new)
- CURRENT body markdown (or empty)
- CURRENT reference files {slug: markdown} (or empty)
- CURRENT scripts {filename: source} (or empty)
- TODAY's reinforcement-feedback JSON

Produce ONE valid JSON object only (no markdown fences, no commentary):
{
  "description": "third-person WHAT + WHEN, <=1024 chars, with concrete trigger terms an agent can match",
  "triggers": ["short phrases that should cause this skill to be selected", "..."],
  "tags": ["product-or-domain", "task-type", "..."],
  "tools": ["tool_or_api_names_this_sandbox_uses"],
  "body_markdown": "full updated SKILL.md body",
  "references": {"workflow": "...", "output_contract": "..."},
  "scripts": {"validate_output.py": "#!/usr/bin/env python3\\n..."}
}

Description rules (critical for routing):
- Third person. Include WHAT the skill does AND WHEN to use it.
- Name the product/persona/task precisely (e.g. MediBuddy health plan advisor, not "insurance help").
- Include distinctive trigger terms from the sandbox system prompt and feedback.
- Bad: "Helps with plans." Good: "Assesses US health-insurance risk and recommends MediBuddy plans. Use when the sandbox is MediBuddy Health Plan Advisor or the user asks to rank eligible MediBuddy plans from member risk + policy evidence."

Body markdown MUST use these headings in order:
## When to use
## What this sandbox is
## Workflow
## Mistakes to avoid
## Things to take care of
## Domain knowledge to assume
## Scripts and tooling
## Positive patterns to keep
## Changelog

Workflow section:
- Summarize the mandatory step sequence in short bullets.
- ALWAYS maintain references/workflow.md containing a ```mermaid flowchart (or sequenceDiagram) of the end-to-end process when the sandbox has a multi-step tool workflow. Link it as `See references/workflow.md`.
- If feedback mentions a strict JSON/schema/output contract, ALWAYS maintain references/output_contract.md with the schema/example and link it. Do not only bury the contract in prose.

Scripts:
- When feedback implies mechanical checks (JSON schema, required fields, arithmetic, ranking rules), add or update a small script under scripts/ (prefer Python) the agent can run, e.g. validate_output.py.
- Scripts must be complete and runnable; include a brief usage comment at the top.
- In ## Scripts and tooling, tell the agent when/how to run each script (e.g. `python scripts/validate_output.py --stdin`).
- If no mechanical check exists, scripts may be {}.

References / scripts merge discipline:
- Carry forward existing files unless today's feedback gives POSITIVE evidence they are wrong.
- Keep body lean: link out instead of pasting huge schemas.
- Never invent tools, policies, or schema fields not implied by feedback or existing skill content.

Other merge rules:
- Consolidate bullets; do not append blindly. Soft cap ~10-12 bullets/section (except Changelog).
- Changelog: keep prior dated lines; add EXACTLY ONE new line for today, most-recent first.
"""

MERGE_ANALYSIS_SYSTEM_PROMPT = """You maintain the ANALYSIS SYSTEM PROMPT used to analyze future conversations
for ONE specific sandbox scenario. This prompt is fed to an LLM as its system message; it is NOT the skill
document itself.

You will receive the CURRENT analysis instructions and TODAY's reinforcement-feedback JSON for this sandbox.
Sharpen the instructions so future analysis of THIS sandbox catches its recurring issues faster and more
precisely - e.g. call out this sandbox's specific mistake patterns, domain facts, or output-contract quirks
to watch for.

Rules:
- You MUST preserve the required JSON response schema EXACTLY as in the current instructions, including
  these exact key names verbatim: title, executive_summary, mistakes, user_hassle_hotspots,
  knowledge_to_internalize, behavior_rules_for_next_run, prompt_additions, prioritized_actions,
  positive_patterns_to_keep. Never rename, remove, or add top-level keys.
- Add/sharpen sandbox-specific guidance (in prose, before or around the schema) about what to look for
  in THIS sandbox's transcripts, based on recurring patterns in the feedback.
- Do not bloat: consolidate, do not just append every day's notes.
- Respond with the FULL updated instructions text only - no markdown fences, no commentary, no JSON wrapper.
"""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "sandbox"


def skill_dir(skills_root: Path, slug: str) -> Path:
    return skills_root / slug


def skill_md_path(skills_root: Path, slug: str) -> Path:
    return skill_dir(skills_root, slug) / "SKILL.md"


def references_dir(skills_root: Path, slug: str) -> Path:
    return skill_dir(skills_root, slug) / "references"


def scripts_dir(skills_root: Path, slug: str) -> Path:
    return skill_dir(skills_root, slug) / "scripts"


def analysis_skill_dir(skills_root: Path, slug: str) -> Path:
    return skill_dir(skills_root, slug) / "analysis-skill"


def _parse_yaml_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        parts = []
        for part in inner.split(","):
            part = part.strip().strip('"').strip("'")
            if part:
                parts.append(part)
        return parts
    if value:
        return [value.strip('"').strip("'")]
    return []


def analysis_skill_md_path(skills_root: Path, slug: str) -> Path:
    return analysis_skill_dir(skills_root, slug) / "SKILL.md"


def next_free_slug(skills_root: Path, base_slug: str) -> str:
    if not skill_dir(skills_root, base_slug).exists():
        return base_slug
    n = 2
    while skill_dir(skills_root, f"{base_slug}-{n}").exists():
        n += 1
    return f"{base_slug}-{n}"


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n\n?", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key in {"triggers", "tags", "tools"}:
            fields[key] = _parse_yaml_list(value)
        elif value.startswith('"') and value.endswith('"'):
            fields[key] = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif re.fullmatch(r"-?\d+", value):
            fields[key] = int(value)
        elif value.lower() in {"true", "false"}:
            fields[key] = value.lower() == "true"
        else:
            fields[key] = value
    return fields


def _yaml_list(items: list[str]) -> str:
    cleaned = [yaml_escape(str(x)) for x in items if str(x).strip()]
    return "[" + ", ".join(f'"{c}"' for c in cleaned) + "]"


def read_skill_body(path: Path) -> tuple[dict[str, Any], str] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    body = _FRONTMATTER_RE.sub("", text, count=1)
    body = re.sub(r"^#\s.*\n\n?", "", body, count=1)
    return frontmatter, body.strip() + "\n"


def render_skill_md(
    *,
    name: str,
    slug: str,
    description: str,
    body_markdown: str,
    created_at: str,
    updated_at: str,
    session_count: int,
    last_active_date: str,
    triggers: list[str] | None = None,
    tags: list[str] | None = None,
    tools: list[str] | None = None,
) -> str:
    # Agent Skill frontmatter: `name` + rich `description` are the primary router signals.
    # Extra fields (triggers/tags/tools) help classify.py + catalog.json matching.
    front = "\n".join(
        [
            "---",
            f'name: "{yaml_escape(slug)}"',
            f'display_name: "{yaml_escape(name)}"',
            f'slug: "{yaml_escape(slug)}"',
            f'description: "{yaml_escape(description)}"',
            f"triggers: {_yaml_list(triggers or [])}",
            f"tags: {_yaml_list(tags or [])}",
            f"tools: {_yaml_list(tools or [])}",
            f'created_at: "{yaml_escape(created_at)}"',
            f'updated_at: "{yaml_escape(updated_at)}"',
            f"session_count: {session_count}",
            f'last_active_date: "{yaml_escape(last_active_date)}"',
            "---",
            "",
        ]
    )
    return f"{front}# {name}\n\n{body_markdown.strip()}\n"


def render_analysis_skill_md(*, sandbox_name: str, slug: str, instructions_body: str) -> str:
    analysis_name = f"{slug}-analysis"
    description = (
        f"Use this to analyze future SME-agent conversations for the {sandbox_name} sandbox and "
        "produce the reinforcement-feedback JSON (title, executive_summary, mistakes, "
        "user_hassle_hotspots, knowledge_to_internalize, behavior_rules_for_next_run, "
        "prompt_additions, prioritized_actions, positive_patterns_to_keep)."
    )
    front = "\n".join(
        [
            "---",
            f'name: "{yaml_escape(analysis_name)}"',
            f'display_name: "{yaml_escape(sandbox_name)} - Analysis Instructions"',
            f'description: "{yaml_escape(description)}"',
            "---",
            "",
        ]
    )
    return f"{front}# {sandbox_name} - Analysis Instructions\n\n{instructions_body.strip()}\n"


def read_references(skills_root: Path, slug: str) -> dict[str, str]:
    directory = references_dir(skills_root, slug)
    if not directory.exists():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.md"))}


def write_references(skills_root: Path, slug: str, references: dict[str, str]) -> None:
    directory = references_dir(skills_root, slug)
    existing = set(directory.glob("*.md")) if directory.exists() else set()
    keep = set()
    if references:
        directory.mkdir(parents=True, exist_ok=True)
        for file_slug, content in references.items():
            path = directory / f"{slugify(file_slug)}.md"
            path.write_text(content.strip() + "\n", encoding="utf-8")
            keep.add(path)
    for stale in existing - keep:
        stale.unlink()


def read_scripts(skills_root: Path, slug: str) -> dict[str, str]:
    directory = scripts_dir(skills_root, slug)
    if not directory.exists():
        return {}
    out: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix in {".py", ".sh", ".js", ".ts", ".mjs"}:
            out[path.name] = path.read_text(encoding="utf-8")
    return out


def write_scripts(skills_root: Path, slug: str, scripts: dict[str, str]) -> None:
    directory = scripts_dir(skills_root, slug)
    existing = {p for p in directory.iterdir() if p.is_file()} if directory.exists() else set()
    keep: set[Path] = set()
    if scripts:
        directory.mkdir(parents=True, exist_ok=True)
        for filename, content in scripts.items():
            safe = Path(filename).name
            if not re.search(r"\.(py|sh|js|ts|mjs)$", safe):
                safe = f"{slugify(safe)}.py"
            path = directory / safe
            text = content.strip() + "\n"
            path.write_text(text, encoding="utf-8")
            keep.add(path)
    for stale in existing - keep:
        stale.unlink()


def merge_skill_with_llm(
    *,
    existing_body: str,
    sandbox_name: str,
    sandbox_description: str,
    existing_triggers: list[str],
    existing_tags: list[str],
    existing_tools: list[str],
    existing_references: dict[str, str],
    existing_scripts: dict[str, str],
    feedback: dict[str, Any],
    active_date: str,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    user_prompt = (
        f"Sandbox name: {sandbox_name}\n"
        f"Today's date: {active_date}\n\n"
        f"CURRENT description:\n{sandbox_description or '(none yet - brand new sandbox)'}\n\n"
        f"CURRENT triggers: {json.dumps(existing_triggers, ensure_ascii=False)}\n"
        f"CURRENT tags: {json.dumps(existing_tags, ensure_ascii=False)}\n"
        f"CURRENT tools: {json.dumps(existing_tools, ensure_ascii=False)}\n\n"
        f"CURRENT body markdown:\n{existing_body or '(none yet - brand new sandbox)'}\n\n"
        f"CURRENT reference files:\n"
        f"{json.dumps(existing_references, ensure_ascii=False, indent=2) if existing_references else '(none yet)'}\n\n"
        f"CURRENT scripts:\n"
        f"{json.dumps(existing_scripts, ensure_ascii=False, indent=2) if existing_scripts else '(none yet)'}\n\n"
        f"TODAY's reinforcement feedback JSON for this sandbox:\n"
        f"{json.dumps(feedback, ensure_ascii=False, indent=2)}"
    )
    messages = [
        {"role": "system", "content": MERGE_SKILL_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    raw = call_openrouter(messages, model=model, api_key=api_key)
    data = extract_json_object(raw)
    data["references"] = {str(k): str(v) for k, v in (data.get("references") or {}).items()}
    data["scripts"] = {str(k): str(v) for k, v in (data.get("scripts") or {}).items()}
    data["triggers"] = [str(x) for x in (data.get("triggers") or []) if str(x).strip()]
    data["tags"] = [str(x) for x in (data.get("tags") or []) if str(x).strip()]
    data["tools"] = [str(x) for x in (data.get("tools") or []) if str(x).strip()]
    return data


def merge_analysis_instructions_with_llm(
    *,
    existing_instructions: str,
    sandbox_name: str,
    feedback: dict[str, Any],
    model: str,
    api_key: str,
) -> str:
    user_prompt = (
        f"Sandbox name: {sandbox_name}\n\n"
        f"CURRENT analysis instructions:\n{existing_instructions}\n\n"
        f"TODAY's reinforcement feedback JSON for this sandbox:\n"
        f"{json.dumps(feedback, ensure_ascii=False, indent=2)}"
    )
    messages = [
        {"role": "system", "content": MERGE_ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    text = call_openrouter(messages, model=model, api_key=api_key).strip()
    missing = [k for k in REQUIRED_ANALYSIS_KEYS if k not in text]
    if missing:
        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your response is missing required schema key name(s): {', '.join(missing)}. "
                    "Return the FULL corrected instructions text, preserving ALL required key names verbatim."
                ),
            }
        )
        text = call_openrouter(messages, model=model, api_key=api_key).strip()
    return text


def load_index(skills_root: Path) -> dict[str, Any]:
    path = skills_root / "index.json"
    if not path.exists():
        return {"sandboxes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def update_index(
    skills_root: Path,
    *,
    slug: str,
    name: str,
    session_count_delta: int,
    active_date: str,
    description: str = "",
    triggers: list[str] | None = None,
    tags: list[str] | None = None,
    tools: list[str] | None = None,
    has_references: bool = False,
    has_scripts: bool = False,
) -> None:
    skills_root.mkdir(parents=True, exist_ok=True)
    index = load_index(skills_root)
    entry = index["sandboxes"].setdefault(
        slug, {"name": name, "session_count": 0, "last_active_date": active_date}
    )
    entry["name"] = name
    entry["session_count"] = entry.get("session_count", 0) + session_count_delta
    entry["last_active_date"] = active_date
    if description:
        entry["description"] = description
    entry["triggers"] = list(triggers or entry.get("triggers") or [])
    entry["tags"] = list(tags or entry.get("tags") or [])
    entry["tools"] = list(tools or entry.get("tools") or [])
    entry["has_references"] = has_references
    entry["has_scripts"] = has_scripts
    (skills_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_catalog(skills_root: Path) -> Path:
    """Machine-readable skill router catalog for agents (description/triggers/tags)."""
    skills_root.mkdir(parents=True, exist_ok=True)
    catalog: list[dict[str, Any]] = []
    for directory in sorted(skills_root.iterdir()):
        md_path = directory / "SKILL.md"
        if not directory.is_dir() or not md_path.exists():
            continue
        parsed = read_skill_body(md_path)
        if parsed is None:
            continue
        fm, _body = parsed
        slug = str(fm.get("slug") or directory.name)
        refs = sorted(p.name for p in references_dir(skills_root, slug).glob("*.md")) if references_dir(skills_root, slug).exists() else []
        scripts = sorted(read_scripts(skills_root, slug))
        catalog.append(
            {
                "name": slug,
                "display_name": fm.get("display_name") or fm.get("name") or slug,
                "description": fm.get("description") or "",
                "triggers": fm.get("triggers") or [],
                "tags": fm.get("tags") or [],
                "tools": fm.get("tools") or [],
                "path": f"{slug}/SKILL.md",
                "references": refs,
                "scripts": scripts,
                "session_count": fm.get("session_count") or 0,
                "last_active_date": fm.get("last_active_date") or "",
            }
        )
    catalog.sort(key=lambda r: (-int(r.get("session_count") or 0), str(r["name"])))
    out = {
        "schema": "proto2-skill-catalog/1",
        "purpose": "Agent skill router: match incoming sandbox requests to description/triggers/tags, then load path + references/scripts.",
        "skills": catalog,
    }
    path = skills_root / "catalog.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def update_skill_for_sandbox(
    *,
    slug: str,
    name: str,
    description: str,
    feedback: dict[str, Any],
    session_count_today: int,
    active_date: str,
    skills_root: Path,
    model: str,
    api_key: str,
) -> Path:
    directory = skill_dir(skills_root, slug)
    directory.mkdir(parents=True, exist_ok=True)
    md_path = skill_md_path(skills_root, slug)

    existing = read_skill_body(md_path)
    existing_frontmatter, existing_body = existing if existing else ({}, "")
    existing_description = existing_frontmatter.get("description") or description
    existing_triggers = list(existing_frontmatter.get("triggers") or [])
    existing_tags = list(existing_frontmatter.get("tags") or [])
    existing_tools = list(existing_frontmatter.get("tools") or [])
    created_at = existing_frontmatter.get("created_at") or datetime.now(get_tz()).isoformat()
    existing_references = read_references(skills_root, slug)
    existing_scripts = read_scripts(skills_root, slug)

    merged = merge_skill_with_llm(
        existing_body=existing_body,
        sandbox_name=name,
        sandbox_description=existing_description,
        existing_triggers=existing_triggers,
        existing_tags=existing_tags,
        existing_tools=existing_tools,
        existing_references=existing_references,
        existing_scripts=existing_scripts,
        feedback=feedback,
        active_date=active_date,
        model=model,
        api_key=api_key,
    )
    updated_at = datetime.now(get_tz()).isoformat()
    prior_session_count = existing_frontmatter.get("session_count", 0)
    new_description = str(merged.get("description") or existing_description or description)
    new_triggers = list(merged.get("triggers") or existing_triggers)
    new_tags = list(merged.get("tags") or existing_tags)
    new_tools = list(merged.get("tools") or existing_tools)
    new_refs = merged.get("references") or {}
    new_scripts = merged.get("scripts") or {}
    md_path.write_text(
        render_skill_md(
            name=name,
            slug=slug,
            description=new_description,
            body_markdown=str(merged.get("body_markdown") or existing_body),
            created_at=created_at,
            updated_at=updated_at,
            session_count=prior_session_count + session_count_today,
            last_active_date=active_date,
            triggers=new_triggers,
            tags=new_tags,
            tools=new_tools,
        ),
        encoding="utf-8",
    )
    write_references(skills_root, slug, new_refs)
    write_scripts(skills_root, slug, new_scripts)

    # ponytail: bootstrap instructions verbatim on day 1 (no merge call) to match day-1 analysis behavior.
    # Falls back to the pre-migration flat analysis_instructions.md so in-flight sandboxes don't restart.
    analysis_md_path = analysis_skill_md_path(skills_root, slug)
    legacy_instructions_path = directory / "analysis_instructions.md"
    existing_analysis = read_skill_body(analysis_md_path)
    if existing_analysis is not None:
        existing_instructions = existing_analysis[1]
    elif legacy_instructions_path.exists():
        existing_instructions = legacy_instructions_path.read_text(encoding="utf-8")
    else:
        existing_instructions = ""

    if existing_instructions:
        new_instructions = merge_analysis_instructions_with_llm(
            existing_instructions=existing_instructions,
            sandbox_name=name,
            feedback=feedback,
            model=model,
            api_key=api_key,
        )
    else:
        new_instructions = DEFAULT_ANALYSIS_INSTRUCTIONS
    analysis_skill_dir(skills_root, slug).mkdir(parents=True, exist_ok=True)
    analysis_md_path.write_text(
        render_analysis_skill_md(sandbox_name=name, slug=slug, instructions_body=new_instructions),
        encoding="utf-8",
    )
    legacy_instructions_path.unlink(missing_ok=True)

    update_index(
        skills_root,
        slug=slug,
        name=name,
        session_count_delta=session_count_today,
        active_date=active_date,
        description=new_description,
        triggers=new_triggers,
        tags=new_tags,
        tools=new_tools,
        has_references=bool(new_refs),
        has_scripts=bool(new_scripts),
    )
    write_catalog(skills_root)
    return md_path
