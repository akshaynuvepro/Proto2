"""Deterministic compiler from a selected principle bank to one improvement skill."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import (
    AssessmentImprovementPrinciple,
    PrincipleBankVersion,
    SchemaError,
    content_hash,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "doc" / "templates" / "assessment-skill-improver" / "SKILL.md"
REQUIRED_TEMPLATE_SECTIONS = {
    "Mission",
    "Non-Goals",
    "Input Contract",
    "Trust Boundaries",
    "Learner-Comprehension Boundary",
    "Output Contract",
    "Validation Checklist",
    "High-Risk Action Blacklist",
}


@dataclass(slots=True)
class CompilationResult:
    skill_markdown: str
    manifest: dict[str, Any]


def _headings(text: str) -> set[str]:
    return {
        line.removeprefix("## ").strip()
        for line in text.splitlines()
        if line.startswith("## ")
    }


def compile_improvement_skill(
    bank: PrincipleBankVersion,
    *,
    template_path: Path = DEFAULT_TEMPLATE,
    token_budget: int = 8000,
) -> CompilationResult:
    bank.validate()
    if bank.pareto_status not in {"selected", "frontier"}:
        raise SchemaError("only a selected/frontier bank may be compiled")
    template = template_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    missing = REQUIRED_TEMPLATE_SECTIONS - _headings(template)
    if missing:
        raise SchemaError(f"seed template is missing mandatory sections: {sorted(missing)}")
    principles = [
        AssessmentImprovementPrinciple.from_dict(raw) for raw in bank.principles
    ]
    approved = [
        principle
        for principle in principles
        if principle.review_status in {"approved", "approved_with_edits"}
    ]
    excluded = [
        {
            "principle_id": principle.principle_id,
            "reason": f"review_status={principle.review_status}",
        }
        for principle in principles
        if principle not in approved
    ]
    section = _render_principles(approved, bank)
    marker = "\n## Changelog\n"
    if marker not in template:
        raise SchemaError("seed template lacks Changelog insertion anchor")
    compiled = template.replace(marker, f"\n{section}\n{marker}", 1)
    estimated_tokens = max(1, int(len(compiled.split()) * 1.33))
    if estimated_tokens > token_budget:
        raise SchemaError(
            f"compiled skill exceeds token budget: {estimated_tokens} > {token_budget}"
        )
    manifest = {
        "schema_version": "improvement-skill-compilation/1",
        "bank_id": bank.bank_id,
        "bank_content_hash": bank.content_hash,
        "template_path": str(template_path.relative_to(ROOT)).replace("\\", "/"),
        "template_hash": content_hash(template),
        "compiled_hash": content_hash(compiled),
        "included_principle_versions": [
            f"{item.principle_id}:v{item.version}" for item in approved
        ],
        "excluded_principles": excluded,
        "estimated_tokens": estimated_tokens,
        "token_budget": token_budget,
        "required_sections_present": True,
        "deterministic": True,
    }
    return CompilationResult(skill_markdown=compiled, manifest=manifest)


def _render_principles(
    principles: list[AssessmentImprovementPrinciple],
    bank: PrincipleBankVersion,
) -> str:
    lines = [
        "## Optimized Evidence-Backed Principles",
        "",
        f"Principle bank: {bank.bank_id}, version {bank.version}.",
        "",
        "Apply these rules only within their declared boundaries. The governing",
        "contracts and safety rules elsewhere in this skill take precedence.",
        "",
    ]
    for index, principle in enumerate(
        sorted(principles, key=lambda item: (item.title.lower(), item.principle_id)), 1
    ):
        lines.extend(
            [
                f"### P{index}: {principle.title}",
                "",
                principle.principle,
                "",
                "Apply when:",
                *[f"- {value}" for value in principle.when_to_apply],
                "",
                "Do not apply when:",
                *(
                    [f"- {value}" for value in principle.when_not_to_apply]
                    if principle.when_not_to_apply
                    else ["- No additional exception beyond governing contracts is approved."]
                ),
                "",
                f"Failure mechanism: {principle.failure_mechanism}",
                "",
                "Procedure:",
                *[f"{step}. {value}" for step, value in enumerate(principle.remedy, 1)],
                "",
                "Never:",
                *[f"- {value}" for value in principle.high_risk_blacklist],
                "",
                "Validate:",
                *[f"- {value}" for value in principle.validation_expectations],
                "",
                "Evidence: "
                + ", ".join(
                    [
                        *principle.positive_example_ids,
                        *principle.negative_example_ids,
                        *principle.learner_cluster_ids,
                    ]
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip()
