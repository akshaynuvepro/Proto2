from __future__ import annotations

import json
from typing import Any

from openrouter import OpenRouterSettings, strip_code_fence

from .agent import run_agent
from .metrics import compute_automatic_metrics
from .models import Assessment
from .tools_aws import ToolContext, make_handlers, tool_definitions

SYSTEM = """You are an SME assessment comparator agent with tools.

Workflow:
1. Call list_assessments for holdout and generated sets.
2. Inspect several assessments via get_assessment and run_structure_check (at least 2 holdout + 2 generated).
3. Use lookup_aws_service / search_aws_wellarchitected when AWS correctness or lab craft matters.
4. Optionally compute_text_overlap for candidate pairs.
5. When ready, stop calling tools and return ONLY valid JSON:

{
  "summary_markdown": "human-readable report with overall verdict and top gaps",
  "overall_score": 0.0,
  "dimensions": {
    "house_style": {"score": 0.0, "notes": "..."},
    "structure": {"score": 0.0, "notes": "..."},
    "depth": {"score": 0.0, "notes": "..."},
    "clarity": {"score": 0.0, "notes": "..."},
    "completeness": {"score": 0.0, "notes": "..."}
  },
  "pairs": [
    {
      "generated_id": "...",
      "holdout_id": "...",
      "score": 0.0,
      "strengths": ["..."],
      "gaps": ["..."]
    }
  ],
  "priority_fixes": [
    {"priority": 1, "issue": "...", "recommendation": "..."}
  ],
  "improvement_brief": "concise brief an improver skill should encode"
}

Scores are 0-10. Be concrete and actionable. Do not invent assessment ids — only use ids from tools.
"""


def _catalog(items: list[Assessment], label: str) -> str:
    lines = [f"{label} ({len(items)}):"]
    for a in items:
        lines.append(f"- {a.id}: {a.title}")
    return "\n".join(lines)


def compare_agent(
    generated: list[Assessment],
    holdout: list[Assessment],
    *,
    settings: OpenRouterSettings | None = None,
    max_rounds: int = 10,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ctx = ToolContext(generated=generated, holdout=holdout)
    tools = tool_definitions(include_report=False)
    handlers = make_handlers(ctx)
    # Drop report/improver handlers that are unused in compare.
    handlers = {k: handlers[k] for k in handlers if k in {t["function"]["name"] for t in tools}}

    user = (
        f"{_catalog(holdout, 'HOLDOUT SME ASSESSMENTS')}\n\n"
        f"{_catalog(generated, 'GENERATED ASSESSMENTS')}\n\n"
        "Use tools to inspect several assessments before scoring. "
        "Then produce the comparison JSON."
    )
    result = run_agent(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        tools=tools,
        handlers=handlers,
        settings=settings,
        max_rounds=max_rounds,
        max_tokens=8192,
        response_format={"type": "json_object"},
    )
    report = json.loads(strip_code_fence(result.text))
    if "summary_markdown" not in report:
        report["summary_markdown"] = report.get("improvement_brief") or json.dumps(report, indent=2)
    report["agent_trace"] = result.trace
    report["automatic_metrics"] = compute_automatic_metrics(
        generated,
        holdout,
        pairs=report.get("pairs") if isinstance(report.get("pairs"), list) else None,
        settings=settings,
    )
    meta = {**result.meta, "agent_rounds": result.rounds, "tools_used": [t["tool"] for t in result.trace]}
    return report, meta
