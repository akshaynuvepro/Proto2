"""Synthetic, domain-neutral fixtures. These are never AWS validation data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .normalization import normalize_conversation
from .schemas import (
    BenchmarkItem,
    DomainProfile,
    EvidenceBundle,
    TargetSkillEnvelope,
    content_hash,
)


TARGET_SKILL = """---
name: fixture-assessment-generator
description: Generates domain-neutral scenario assessments for contract tests.
---

# Fixture Assessment Generator

## Workflow

1. Read the supplied objective and level.
2. Create one scenario question.
3. State the task without providing its answer.

## Output Contract

Return a question, an evaluator-only rubric, and the phrase REQUIRED-MARKER.

## Protected Policy

Do not reveal answers, commands, or evaluator secrets to the learner.
"""


def domain_profile() -> DomainProfile:
    profile = DomainProfile(
        profile_id="fixture-domain:v1",
        version="v1",
        domain="synthetic-fixture",
        authoritative_terminology={
            "observable output": "A result a reviewer can inspect without prescribing its creation."
        },
        competency_taxonomy=[
            {"id": "fixture-analysis", "label": "Analyze a constrained scenario"}
        ],
        assessment_types=["scenario", "hands-on"],
        difficulty_model={
            "levels": ["beginner", "intermediate", "advanced"],
            "protected": True,
        },
        protected_policies=[
            "Never disclose the evaluator-only rubric to the learner.",
            "Never provide a solution path.",
        ],
        approved_references=[
            {"id": "fixture-reference", "authority": "synthetic-test-only"}
        ],
        validators=[{"id": "fixture-required-marker", "version": "1"}],
        prohibited_behavior=["Domain-specific factual claims", "Learner solutions"],
        owner="fixture-owner",
        approved=True,
    )
    profile.validate()
    return profile


def target_envelope() -> TargetSkillEnvelope:
    protected = (
        "## Protected Policy\n\n"
        "Do not reveal answers, commands, or evaluator secrets to the learner.\n"
    )
    envelope = TargetSkillEnvelope(
        target_skill_id="fixture-assessment-generator",
        display_name="Fixture Assessment Generator",
        input_version="v1",
        input_content_hash=content_hash(TARGET_SKILL),
        exact_skill_markdown=TARGET_SKILL,
        domain_profile_id="fixture-domain:v1",
        owner="fixture-owner",
        status="staging",
        required_frontmatter={
            "name": {"required": True, "immutable": True, "type": "string"},
            "description": {"required": True, "immutable": False, "type": "string"},
        },
        immutable_sections={"Protected Policy": content_hash(protected)},
        required_sections=["Workflow", "Output Contract", "Protected Policy"],
        input_contract={"required": ["objective", "level"]},
        output_contract={"required_literals": ["REQUIRED-MARKER"]},
        tool_contracts=[],
        script_contracts=[],
        reference_contracts=[],
        protected_behaviors=[
            {"id": "no-solutions", "description": "No learner-facing solution"}
        ],
        permitted_change_areas=["Workflow"],
        validators=[{"id": "fixture-contract-validator", "version": "1"}],
        rollback={"previous_version": "v1", "owner": "fixture-owner"},
        metadata={"synthetic_fixture": True},
    )
    envelope.validate()
    return envelope


def approved_evidence_item(evidence_id: str = "sme_ev_fixture_observable") -> dict[str, Any]:
    return {
        "schema_version": "sme-evidence/1",
        "evidence_id": evidence_id,
        "category": "correction_pair",
        "claim": "State an observable completion outcome without prescribing the solution path.",
        "rationale": "The learner must know what artifact is evaluated while retaining the intended challenge.",
        "failure_mechanism": "Activity-only instructions do not define a reviewable end state.",
        "recommended_behavior": "Name the observable output and acceptance boundary without commands.",
        "before": {"summary": "Instruction names activity only."},
        "after": {"summary": "Instruction names an observable output."},
        "positive_example": None,
        "negative_example": None,
        "applicability": {
            "domains": [],
            "assessment_types": ["scenario", "hands-on"],
        },
        "exceptions": ["The output itself is intentionally the discovery target."],
        "source_spans": [
            {
                "schema_version": "source-span/1",
                "span_id": "span_fixture_sme",
                "conversation_id": "conv_fixture_sme",
                "message_id": "msg_fixture_sme",
                "start_char": 0,
                "end_char": 20,
                "text_hash": content_hash("approved fixture span"),
                "sanitized_excerpt": "approved fixture span",
                "redaction_labels": [],
            }
        ],
        "extractor_confidence": 1.0,
        "inference_level": "explicit",
        "review_status": "approved",
        "supersedes": [],
        "created_by": {"component": "fixture"},
        "created_at": "2026-08-07T00:00:00+00:00",
    }


def evidence_bundle_payload() -> dict[str, Any]:
    manifest = EvidenceBundle(
        bundle_id="bundle_fixture_v1",
        created_at="2026-08-07T00:00:00+00:00",
        cutoff_at="2026-08-07T00:00:00+00:00",
        domain_profile_id="fixture-domain:v1",
        target_scope=["fixture-assessment-generator"],
        sme_evidence_ids=["sme_ev_fixture_observable"],
        learner_cluster_ids=[],
        excluded_evidence=[],
        split_manifest="fixture-splits:v1",
        review_manifest="fixture-reviews:v1",
        statistics={
            "sme_positive_anchors": 0,
            "sme_correction_pairs": 1,
            "learner_confusion_clusters": 0,
            "distinct_smes": 1,
            "distinct_learners": 0,
        },
        content_hash="",
    )
    raw = manifest.to_dict()
    raw["content_hash"] = ""
    manifest.content_hash = content_hash(raw)
    manifest.validate()
    return {"manifest": manifest.to_dict(), "items": [approved_evidence_item()]}


def benchmark_item(split: str, index: int) -> BenchmarkItem:
    item = BenchmarkItem(
        id=f"fixture_{split}_{index}",
        split=split,
        split_group=f"fixture-family-{split}-{index}",
        target_skill_envelope=target_envelope().to_dict(),
        domain_profile=domain_profile().to_dict(),
        assessment_brief={
            "objective": f"Analyze synthetic scenario variant {split}-{index}",
            "level": ["beginner", "intermediate", "advanced"][index % 3],
            "required_literals": ["REQUIRED-MARKER"],
            "prohibited_literals": ["THE-ANSWER-IS"],
            "minimum_characters": 40,
        },
        evidence_bundle=evidence_bundle_payload(),
        expected_behaviors=[
            {
                "dimension": "instruction_clarity",
                "required_phrases": ["observable"],
                "prohibited_phrases": ["step-by-step solution"],
            },
            {
                "dimension": "sme_adaptation",
                "required_phrases": ["observable"],
            },
            {
                "dimension": "assessment_utility",
                "required_phrases": ["scenario", "REQUIRED-MARKER"],
            },
            {
                "dimension": "objective_coverage",
                "required_phrases": ["analyze"],
            },
        ],
        protected_behaviors=[
            {"id": "no-solution", "required": True},
            {"id": "required-marker", "required": True},
        ],
        deterministic_validators=[
            "target-contract:v1",
            "assessment-required-content:v1",
            "solution-leakage:v1",
        ],
        consumer_config={
            "paired": True,
            "temperature": 0,
            "synthetic_fixture": True,
        },
        expected_output=None,
        metadata={
            "assessment_type": "scenario" if index % 2 == 0 else "hands-on",
            "level": ["beginner", "intermediate", "advanced"][index % 3],
            "synthetic_fixture": True,
        },
    )
    item.validate()
    return item


def synthetic_sme_conversation():
    return normalize_conversation(
        source="synthetic-fixture",
        source_conversation_id="sme-1",
        messages=[
            {
                "role": "user",
                "content": (
                    "Revise the instruction: require an observable output instead of "
                    "listing the steps. Do not reveal commands. This preserves the "
                    "intermediate difficulty."
                ),
            },
            {
                "role": "assistant",
                "content": "The assessment now asks for a reviewable artifact without a procedure.",
            },
            {
                "role": "user",
                "content": "Approved. The rubric must evaluate the objective and observable state.",
            },
        ],
        persona="sme",
        participant_ids=["fixture-sme"],
        assessment_id="fixture-assessment",
        assessment_version="v1",
        target_skill_id="fixture-assessment-generator",
        domain="synthetic-fixture",
        consent={
            "assessment_improvement": True,
            "llm_processing": True,
            "telemetry_redacted": True,
        },
        retention_class="synthetic-public",
        metadata={"synthetic_fixture": True},
    )


def synthetic_learner_conversations():
    return [
        normalize_conversation(
            source="synthetic-fixture",
            source_conversation_id=f"learner-{index}",
            messages=[
                {
                    "role": "user",
                    "content": "The instruction is not clear about which output I must submit.",
                }
            ],
            persona="learner",
            participant_ids=[f"fixture-learner-{index}"],
            assessment_id="fixture-assessment",
            assessment_version="v1",
            target_skill_id="fixture-assessment-generator",
            domain="synthetic-fixture",
            consent={
                "assessment_improvement": True,
                "llm_processing": True,
                "telemetry_redacted": True,
            },
            retention_class="synthetic-public",
            metadata={"synthetic_fixture": True},
        )
        for index in range(1, 4)
    ]


def materialize_skillopt_fixtures(root: Path) -> list[Path]:
    paths = []
    for split, count in (("train", 3), ("validation", 2), ("test", 2)):
        directory = root / ("val" if split == "validation" else split)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "items.json"
        payload = [benchmark_item(split, index).to_dict() for index in range(1, count + 1)]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


if __name__ == "__main__":
    output = Path(__file__).resolve().parent.parent / "fixtures" / "assessment_improver"
    for fixture_path in materialize_skillopt_fixtures(output):
        print(fixture_path)
