"""Evidence-backed principle distillation and multi-objective bank curation."""

from __future__ import annotations

import copy
import re
from dataclasses import asdict
from itertools import combinations
from typing import Any, Iterable

from .schemas import (
    AssessmentImprovementPrinciple,
    PrincipleBankVersion,
    SMEEvidence,
    SchemaError,
    content_hash,
    stable_id,
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _principle_text(principle: AssessmentImprovementPrinciple) -> str:
    return " ".join(
        [
            principle.title,
            principle.principle,
            principle.failure_mechanism,
            *principle.when_to_apply,
            *principle.remedy,
        ]
    )


def finalize_principle(principle: AssessmentImprovementPrinciple) -> AssessmentImprovementPrinciple:
    raw = asdict(principle)
    raw["content_hash"] = ""
    principle.content_hash = content_hash(raw)
    principle.validate()
    return principle


def finalize_bank(bank: PrincipleBankVersion) -> PrincipleBankVersion:
    raw = asdict(bank)
    raw["content_hash"] = ""
    bank.content_hash = content_hash(raw)
    bank.validate()
    return bank


def distill_sme_evidence(
    evidence: Iterable[SMEEvidence],
) -> list[AssessmentImprovementPrinciple]:
    """Create conservative one-evidence candidates for later model merge/curation."""
    out = []
    for item in evidence:
        item.validate()
        if item.review_status not in {"approved", "approved_with_edits"}:
            raise SchemaError(f"cannot distill unapproved evidence {item.evidence_id}")
        action = item.recommended_behavior or item.claim
        negative = item.category in {
            "correction_pair",
            "rejected_choice",
            "negative_example",
        }
        title_words = re.findall(r"[A-Za-z0-9]+", action)[:8]
        title = " ".join(title_words).strip().capitalize() or "Apply approved assessment behavior"
        identity = {
            "title": title.lower(),
            "category": item.category,
            "evidence": item.evidence_id,
        }
        applicability = item.applicability or {}
        principle = AssessmentImprovementPrinciple(
            principle_id=stable_id("prn", identity),
            title=title,
            principle=_imperative(action),
            when_to_apply=_conditions(applicability),
            when_not_to_apply=list(item.exceptions),
            failure_mechanism=item.failure_mechanism
            or "The target assessment skill does not consistently reproduce this approved SME decision.",
            remedy=[_imperative(action)],
            high_risk_blacklist=[
                "Do not invent domain policy absent from the domain profile.",
                "Do not reveal learner solutions, hints, or evaluator secrets.",
            ],
            validation_expectations=[
                "The evolved target cites the approved evidence for this change.",
                "Paired assessment evaluation shows no protected-behavior regression.",
            ],
            positive_example_ids=[] if negative else [item.evidence_id],
            negative_example_ids=[item.evidence_id] if negative else [],
            learner_cluster_ids=[],
            assessment_types=list(applicability.get("assessment_types") or []),
            domains=list(applicability.get("domains") or []),
            target_capabilities=["structured-assessment-skill-editing"],
            confidence=item.extractor_confidence,
            review_status="pending",
            coverage_clusters=[item.category],
        )
        out.append(finalize_principle(principle))
    return out


def distill_learner_clusters(
    clusters: Iterable[dict[str, Any]],
) -> list[AssessmentImprovementPrinciple]:
    """Turn SME-approved recurring comprehension defects into bounded rules."""
    out = []
    remedy_by_category = {
        "instruction_ambiguity": "Clarify the requested action and observable completion boundary.",
        "undefined_terminology": "Define the ambiguous assessment term without disclosing an answer.",
        "expected_output_unclear": "State the accepted output representation and observable end state.",
        "assessment_scope_unclear": "State the assessed scope and explicit exclusions.",
        "environment_or_tool_confusion": "State where the assessment occurs and which approved tool is expected.",
        "navigation_confusion": "Clarify non-solution navigation needed to reach the assessment surface.",
        "prerequisite_not_communicated": "State required access and prerequisites before the task begins.",
        "feedback_unclear": "Clarify what the assessment feedback refers to without revealing evaluator secrets.",
        "conflicting_requirements": "Resolve or explicitly scope the conflicting learner-facing requirements.",
        "example_or_format_mismatch": "Align the non-answer example with the declared output format.",
    }
    for cluster in clusters:
        if cluster.get("review_status") not in {"approved", "approved_with_edits"}:
            raise SchemaError(
                f"cannot distill unapproved learner cluster {cluster.get('cluster_id')}"
            )
        if cluster.get("solution_leakage_check") != "passed":
            raise SchemaError("learner cluster failed the solution boundary")
        cluster_id = str(cluster.get("cluster_id") or "")
        category = str(cluster.get("category") or "")
        remedy = remedy_by_category.get(
            category,
            "Clarify the assessment-comprehension defect without changing the solution path.",
        )
        principle = AssessmentImprovementPrinciple(
            principle_id=stable_id(
                "prn",
                {"learner_cluster_id": cluster_id, "category": category},
            ),
            title=f"Resolve recurring {category.replace('_', ' ')}",
            principle=(
                "Address this recurring, SME-confirmed learner-comprehension defect "
                "without changing the assessed reasoning or revealing a solution."
            ),
            when_to_apply=[
                f"The target applies to assessment {cluster.get('assessment_id') or 'the reviewed family'}.",
                f"The affected element is {cluster.get('assessment_element_id') or 'the reviewed learner-facing instruction'}.",
            ],
            when_not_to_apply=[
                "The learner signal is a subject knowledge gap rather than an assessment-comprehension defect.",
                "The clarification would expose an answer, hint, command, or solution strategy.",
            ],
            failure_mechanism=str(cluster.get("summary") or category),
            remedy=[
                remedy,
                "Preserve difficulty, competency coverage, and evaluator-only information.",
                "Verify the revision with a solution-leakage check and SME review.",
            ],
            high_risk_blacklist=[
                "Do not include learner quotations containing attempted solutions.",
                "Do not add commands, code, answers, hints, or procedural next steps.",
                "Do not lower difficulty solely because learners struggled.",
            ],
            validation_expectations=[
                "A learner can identify what the assessment asks and what output is expected.",
                "No answer-bearing or strategy-bearing content is introduced.",
                "Protected assessment behavior does not regress.",
            ],
            learner_cluster_ids=[cluster_id],
            target_capabilities=["learner-facing-instruction-editing"],
            confidence=min(
                1.0,
                0.5 + 0.1 * int(cluster.get("distinct_learner_count") or 0),
            ),
            review_status="pending",
            coverage_clusters=[category],
        )
        out.append(finalize_principle(principle))
    return out


def _imperative(text: str) -> str:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return "Apply the approved assessment behavior."
    return cleaned[0].upper() + cleaned[1:]


def _conditions(applicability: dict[str, Any]) -> list[str]:
    conditions = []
    for key in ("assessment_types", "difficulty", "domains", "conditions"):
        values = applicability.get(key) or []
        if isinstance(values, str):
            values = [values]
        if values:
            conditions.append(f"{key.replace('_', ' ').title()}: {', '.join(map(str, values))}")
    return conditions or ["The cited evidence applicability matches the target assessment request."]


def principles_from_model(items: Iterable[dict[str, Any]]) -> list[AssessmentImprovementPrinciple]:
    """Strictly validate model-distilled principles without fabricating citations."""
    out = []
    for supplied in items:
        raw = copy.deepcopy(supplied)
        raw["schema_version"] = AssessmentImprovementPrinciple.SCHEMA
        raw.setdefault(
            "principle_id",
            stable_id(
                "prn",
                {
                    "title": raw.get("title"),
                    "principle": raw.get("principle"),
                    "citations": [
                        *(raw.get("positive_example_ids") or []),
                        *(raw.get("negative_example_ids") or []),
                        *(raw.get("learner_cluster_ids") or []),
                    ],
                },
            ),
        )
        raw.setdefault("content_hash", "")
        principle = AssessmentImprovementPrinciple.from_dict(raw)
        out.append(finalize_principle(principle))
    return out


def diagnose_bank(
    current: Iterable[AssessmentImprovementPrinciple],
    candidates: Iterable[AssessmentImprovementPrinciple],
    *,
    redundancy_threshold: float = 0.82,
) -> list[dict[str, Any]]:
    current_items = list(current)
    operations: list[dict[str, Any]] = []
    for item in current_items:
        item.validate()
        operations.append(
            {
                "operation": "KEEP",
                "principle_id": item.principle_id,
                "reason": "Retained until evidence or measured utility supports a rewrite or removal.",
            }
        )
    for candidate in candidates:
        candidate.validate()
        closest = max(
            current_items,
            key=lambda existing: _jaccard(_principle_text(existing), _principle_text(candidate)),
            default=None,
        )
        similarity = (
            _jaccard(_principle_text(closest), _principle_text(candidate)) if closest else 0.0
        )
        if closest and similarity >= redundancy_threshold:
            operations.append(
                {
                    "operation": "REWRITE",
                    "principle_id": closest.principle_id,
                    "candidate": candidate.to_dict(),
                    "similarity": round(similarity, 4),
                    "reason": "Candidate overlaps an existing principle and should be verified as a rewrite.",
                }
            )
        else:
            operations.append(
                {
                    "operation": "ADD",
                    "principle_id": candidate.principle_id,
                    "candidate": candidate.to_dict(),
                    "similarity": round(similarity, 4),
                    "reason": "Approved evidence is not covered by an existing principle.",
                }
            )
    return operations


def apply_bank_operations(
    current: Iterable[AssessmentImprovementPrinciple],
    operations: Iterable[dict[str, Any]],
) -> list[AssessmentImprovementPrinciple]:
    by_id = {item.principle_id: copy.deepcopy(item) for item in current}
    for operation in operations:
        kind = str(operation.get("operation") or "").upper()
        principle_id = str(operation.get("principle_id") or "")
        if kind == "KEEP":
            if principle_id not in by_id:
                raise SchemaError(f"KEEP references missing principle {principle_id}")
            continue
        if kind == "REMOVE":
            if not operation.get("positive_evidence"):
                raise SchemaError("REMOVE requires positive_evidence")
            by_id.pop(principle_id, None)
            continue
        if kind not in {"ADD", "REWRITE"}:
            raise SchemaError(f"unsupported bank operation {kind}")
        candidate = AssessmentImprovementPrinciple.from_dict(operation.get("candidate") or {})
        if kind == "REWRITE":
            previous = by_id.get(principle_id)
            if previous is None:
                raise SchemaError(f"REWRITE references missing principle {principle_id}")
            candidate.principle_id = previous.principle_id
            candidate.version = previous.version + 1
            candidate.parent_version_id = f"{previous.principle_id}:v{previous.version}"
            candidate = finalize_principle(candidate)
        by_id[candidate.principle_id] = candidate
    return sorted(by_id.values(), key=lambda item: (item.title.lower(), item.principle_id))


def bank_metrics(
    principles: Iterable[AssessmentImprovementPrinciple],
    *,
    expected_evidence_ids: Iterable[str],
    measured_utility: float,
    risk_penalty: float = 0.0,
) -> dict[str, float | int]:
    items = list(principles)
    cited = {
        evidence_id
        for item in items
        for evidence_id in [
            *item.positive_example_ids,
            *item.negative_example_ids,
            *item.learner_cluster_ids,
        ]
    }
    expected = set(expected_evidence_ids)
    similarities = [
        _jaccard(_principle_text(left), _principle_text(right))
        for left, right in combinations(items, 2)
    ]
    diversity = 1 - (sum(similarities) / len(similarities)) if similarities else 1.0
    coverage = len(cited & expected) / len(expected) if expected else 1.0
    compiled_tokens = sum(len(_principle_text(item).split()) for item in items)
    return {
        "utility": round(max(0.0, min(1.0, measured_utility)), 6),
        "diversity": round(max(0.0, min(1.0, diversity)), 6),
        "coverage": round(max(0.0, min(1.0, coverage)), 6),
        "risk_penalty": round(max(0.0, min(1.0, risk_penalty)), 6),
        "compiled_tokens": compiled_tokens,
    }


def create_bank(
    *,
    principles: Iterable[AssessmentImprovementPrinciple],
    evidence_bundle_id: str,
    proposal_id: str,
    objectives: dict[str, float | int],
    operations: list[dict[str, Any]],
    version: int = 1,
    parent_bank_version: str | None = None,
    hard_gates_passed: bool = False,
) -> PrincipleBankVersion:
    items = list(principles)
    identity = {
        "parent": parent_bank_version,
        "bundle": evidence_bundle_id,
        "proposal": proposal_id,
        "principles": [item.content_hash for item in items],
    }
    bank = PrincipleBankVersion(
        bank_id=stable_id("bank", identity),
        version=version,
        parent_bank_version=parent_bank_version,
        principle_versions=[f"{item.principle_id}:v{item.version}" for item in items],
        evidence_bundle_id=evidence_bundle_id,
        proposal_id=proposal_id,
        objectives=objectives,
        hard_gates_passed=hard_gates_passed,
        principles=[item.to_dict() for item in items],
        proposal_operations=copy.deepcopy(operations),
    )
    return finalize_bank(bank)


def pareto_frontier(banks: Iterable[PrincipleBankVersion]) -> list[PrincipleBankVersion]:
    candidates = [bank for bank in banks if bank.hard_gates_passed]
    frontier = []
    for candidate in candidates:
        dominated = any(_dominates(other, candidate) for other in candidates if other is not candidate)
        if not dominated:
            candidate.pareto_status = "frontier"
            finalize_bank(candidate)
            frontier.append(candidate)
        else:
            candidate.pareto_status = "rejected"
            finalize_bank(candidate)
    return sorted(frontier, key=_selection_key)


def select_bank(banks: Iterable[PrincipleBankVersion]) -> PrincipleBankVersion:
    frontier = pareto_frontier(banks)
    if not frontier:
        raise SchemaError("no bank candidate passed hard gates")
    selected = frontier[0]
    selected.pareto_status = "selected"
    return finalize_bank(selected)


def _dominates(left: PrincipleBankVersion, right: PrincipleBankVersion) -> bool:
    maximize = ("utility", "diversity", "coverage")
    minimize = ("risk_penalty", "compiled_tokens")
    no_worse = all(float(left.objectives.get(key, 0)) >= float(right.objectives.get(key, 0)) for key in maximize)
    no_worse = no_worse and all(float(left.objectives.get(key, 0)) <= float(right.objectives.get(key, 0)) for key in minimize)
    strictly = any(float(left.objectives.get(key, 0)) > float(right.objectives.get(key, 0)) for key in maximize)
    strictly = strictly or any(float(left.objectives.get(key, 0)) < float(right.objectives.get(key, 0)) for key in minimize)
    return no_worse and strictly


def _selection_key(bank: PrincipleBankVersion) -> tuple[float, float, float, float, int, str]:
    objectives = bank.objectives
    return (
        -float(objectives.get("utility", 0)),
        float(objectives.get("negative_transfer_count", 0)),
        -float(objectives.get("coverage", 0)),
        float(objectives.get("risk_penalty", 0)),
        int(objectives.get("compiled_tokens", 0)),
        bank.bank_id,
    )
