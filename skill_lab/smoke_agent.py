"""Smoke: tool handlers offline; optional tiny live compare if OPENROUTER_API_KEY set."""

from __future__ import annotations

import json
import os
import sys

from openrouter import load_dotenv
from skill_lab.models import Assessment, SkillPackage
from skill_lab.tools_aws import ToolContext, make_handlers, tool_definitions


def _sample() -> tuple[list[Assessment], list[Assessment], SkillPackage]:
    holdout = [
        Assessment(
            id="h1",
            title="S3 Secure Static Site",
            body=(
                "# S3 Secure Static Site\n\nDuration: 45 minutes\n\n"
                "## Phase 1 — Bucket\nCreate bucket `lab-static-prod` with SSE-S3.\n\n"
                "## Phase 2 — Policy\nAttach least-privilege IAM role.\n\n"
                "## Validation\nObject GET succeeds; public write denied.\n"
            ),
            source="holdout",
        ),
        Assessment(
            id="h2",
            title="Lambda + SQS Worker",
            body=(
                "# Lambda + SQS Worker\n\n**Duration:** 60 mins\n\n"
                "### Task 1\nCreate queue `orders-dlq` and worker Lambda.\n\n"
                "### Task 2\nWire event source mapping; CloudWatch alarm on errors.\n"
            ),
            source="holdout",
        ),
    ]
    generated = [
        Assessment(
            id="g1",
            title="S3 Website Lab",
            body=(
                "# S3 Website Lab\n\nWhat You Will Learn\n\n"
                "Upload files to S3 and enable static hosting.\n"
            ),
            source="generated",
        ),
        Assessment(
            id="g2",
            title="Serverless Queue Processing",
            body=(
                "# Serverless Queue Processing\n\nDuration: 30 minutes\n\n"
                "## Phase 1\nCreate SQS queue.\n\n## Phase 2\nAttach Lambda.\n"
            ),
            source="generated",
        ),
    ]
    skill = SkillPackage(
        files={
            "SKILL.md": "# Assessment Author\nWrite timed AWS lab assessments with phases and validation.\n",
            "references/house-style.md": "Prefer SME tone over tutorial course language.\n",
        },
        summary="sample",
    )
    return generated, holdout, skill


def test_handlers() -> None:
    generated, holdout, skill = _sample()
    report = {
        "overall_score": 5.0,
        "priority_fixes": [{"priority": 1, "issue": "tutorial tone", "recommendation": "drop What You Will Learn"}],
        "improvement_brief": "enforce duration + phases",
        "summary_markdown": "ok",
        "dimensions": {"structure": {"score": 4, "notes": "weak"}},
    }
    ctx = ToolContext(generated=generated, holdout=holdout, skill=skill, report=report, improver_md="# Improve\n")
    h = make_handlers(ctx)

    listed = h["list_assessments"]({"source": "all"})
    assert len(listed) == 4, listed

    body = h["get_assessment"]({"id": "h1"})
    assert "lab-static-prod" in body["body"]

    skill_file = h["get_skill_file"]({"path": "SKILL.md"})
    assert "Assessment Author" in skill_file["content"]

    fixes = h["get_comparison_report"]({"section": "priority_fixes"})
    assert fixes["priority_fixes"][0]["priority"] == 1

    struct = h["run_structure_check"]({"id": "g1"})
    tutorial = next(f for f in struct["findings"] if f["check"] == "tutorial_tone")
    assert tutorial["ok"] is False

    aws = h["lookup_aws_service"]({"service": "S3"})
    assert "object storage" in aws["snippet"].lower()

    wa = h["search_aws_wellarchitected"]({"query": "security IAM"})
    assert wa["hits"]

    bleu = h["compute_text_overlap"]({"generated_id": "g2", "holdout_id": "h2"})
    assert "bleu" in bleu

    defs = tool_definitions(include_report=True, include_improver=True)
    names = {d["function"]["name"] for d in defs}
    assert "get_comparison_report" in names and "get_improver_skill" in names
    print("PASS  tool_handlers", flush=True)


def test_live_compare_tiny() -> None:
    load_dotenv()
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("SKIP  live_compare (no OPENROUTER_API_KEY)", flush=True)
        return

    from skill_lab.compare import compare_agent

    generated, holdout, _ = _sample()
    # Avoid burning embedding cost on full path? compare always runs automatic_metrics.
    # Tiny 2+2 is fine.
    report, meta = compare_agent(generated, holdout, max_rounds=6)
    assert "overall_score" in report
    assert "automatic_metrics" in report
    tools = meta.get("tools_used") or []
    print(
        "PASS  live_compare",
        f"score={report.get('overall_score')} tools={tools} rounds={meta.get('agent_rounds')}",
        flush=True,
    )
    print(json.dumps({"agent_trace": report.get("agent_trace"), "tools_used": tools}, indent=2), flush=True)


def main() -> int:
    test_handlers()
    test_live_compare_tiny()
    return 0


if __name__ == "__main__":
    sys.exit(main())
