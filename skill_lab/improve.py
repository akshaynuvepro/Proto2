from __future__ import annotations

import json
from typing import Any

from openrouter import OpenRouterSettings, strip_code_fence

from .agent import run_agent
from .create_skill import _parse_package
from .models import Assessment, SkillPackage
from .tools_aws import ToolContext, make_handlers, tool_definitions

IMPROVER_SYSTEM = """You write an IMPROVEMENT SKILL (markdown) that an agent uses to revise an assessment-authoring skill.

You have tools: read skill files, the comparison report, sample assessments, structure checks, and AWS/WA snippets.
Use tools to ground rewrite rules in real evidence (priority_fixes + weak generated examples + current SKILL.md).
Then stop calling tools and output markdown only for IMPROVER_SKILL.md — no JSON wrapper.
Encode actionable rules: what to add, remove, tighten, and how to verify.
"""

APPLY_SYSTEM = """You revise an assessment-authoring skill package using an improvement skill and a comparison report.

Use tools to read current skill files, the improver skill, priority fixes, and sample assessments as needed.
Then stop calling tools and return ONLY valid JSON:
{
  "summary": "what changed",
  "files": {
    "SKILL.md": "...",
    "references/house-style.md": "...",
    "references/structure.md": "...",
    "references/worked-patterns.md": "..."
  }
}

Preserve useful content; apply priority fixes; keep the same file set unless a new reference is clearly needed.
Keep each file under ~1200 words so the JSON is not truncated.
"""


def create_improvement_skill(
    report: dict[str, Any],
    current: SkillPackage,
    *,
    generated: list[Assessment] | None = None,
    holdout: list[Assessment] | None = None,
    settings: OpenRouterSettings | None = None,
    max_rounds: int = 10,
) -> tuple[str, dict[str, Any]]:
    ctx = ToolContext(
        generated=list(generated or []),
        holdout=list(holdout or []),
        skill=current,
        report=report,
    )
    tools = tool_definitions(include_report=True)
    handlers = make_handlers(ctx)
    handlers = {k: handlers[k] for k in handlers if k in {t["function"]["name"] for t in tools}}

    file_list = ", ".join(sorted(current.files)) or "(empty)"
    user = (
        f"Skill files available: {file_list}\n"
        f"Report overall_score={report.get('overall_score')}; "
        f"priority_fixes count={len(report.get('priority_fixes') or [])}.\n"
        "Use get_comparison_report, get_skill_file, and sample get_assessment/run_structure_check, "
        "then write IMPROVER_SKILL.md."
    )
    result = run_agent(
        [
            {"role": "system", "content": IMPROVER_SYSTEM},
            {"role": "user", "content": user},
        ],
        tools=tools,
        handlers=handlers,
        settings=settings,
        max_rounds=max_rounds,
        max_tokens=6000,
    )
    text = strip_code_fence(result.text).strip()
    meta = {
        **result.meta,
        "agent_rounds": result.rounds,
        "tools_used": [t["tool"] for t in result.trace],
        "agent_trace": result.trace,
    }
    return text, meta


def apply_improvement(
    current: SkillPackage,
    improver_md: str,
    report: dict[str, Any],
    *,
    generated: list[Assessment] | None = None,
    holdout: list[Assessment] | None = None,
    settings: OpenRouterSettings | None = None,
    max_rounds: int = 10,
) -> tuple[SkillPackage, dict[str, Any]]:
    ctx = ToolContext(
        generated=list(generated or []),
        holdout=list(holdout or []),
        skill=current,
        report=report,
        improver_md=improver_md,
    )
    tools = tool_definitions(include_report=True, include_improver=True)
    handlers = make_handlers(ctx)
    handlers = {k: handlers[k] for k in handlers if k in {t["function"]["name"] for t in tools}}

    file_list = ", ".join(sorted(current.files)) or "(empty)"
    user = (
        f"Skill files: {file_list}\n"
        "Use get_improver_skill, get_comparison_report(section=priority_fixes), "
        "and get_skill_file as needed, then return the improved skill package JSON."
    )
    result = run_agent(
        [
            {"role": "system", "content": APPLY_SYSTEM},
            {"role": "user", "content": user},
        ],
        tools=tools,
        handlers=handlers,
        settings=settings,
        max_rounds=max_rounds,
        max_tokens=12000,
        response_format={"type": "json_object"},
    )
    package = _parse_package(result.text)
    if not package.files.get("SKILL.md"):
        package.files = {**current.files, **package.files}
        package.files.setdefault("SKILL.md", current.skill_md)
    meta = {
        **result.meta,
        "agent_rounds": result.rounds,
        "tools_used": [t["tool"] for t in result.trace],
        "agent_trace": result.trace,
    }
    return package, meta
