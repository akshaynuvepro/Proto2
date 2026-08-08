"""Paired downstream evaluation and SkillLens-style transfer reporting."""

from __future__ import annotations

from statistics import mean
from typing import Any, Iterable

from .schemas import EvaluationResult, EvolutionResult, SchemaError, stable_id


DEFAULT_WEIGHTS = {
    "sme_adaptation": 0.20,
    "assessment_utility": 0.20,
    "objective_coverage": 0.10,
    "difficulty_calibration": 0.08,
    "scenario_realism": 0.06,
    "instruction_clarity": 0.10,
    "learner_confusion_response": 0.06,
    "minimality": 0.05,
    "maintainability": 0.05,
    "target_compatibility": 0.05,
    "evidence_grounding": 0.05,
}


def weighted_score(
    scores: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    weights = weights or DEFAULT_WEIGHTS
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise SchemaError("evaluation weights must sum to 1")
    missing = set(weights) - set(scores)
    if missing:
        raise SchemaError(f"soft scores are missing weighted dimensions: {sorted(missing)}")
    for name, score in scores.items():
        if not 0 <= float(score) <= 1:
            raise SchemaError(f"score {name} must be between 0 and 1")
    return round(sum(float(scores[name]) * weight for name, weight in weights.items()), 6)


def evaluate_candidate(
    *,
    benchmark_item_id: str,
    candidate_id: str,
    split: str,
    hard_gates: dict[str, bool],
    soft_scores: dict[str, float],
    baseline_scores: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    protected_dimensions: Iterable[str] = (
        "objective_coverage",
        "difficulty_calibration",
        "target_compatibility",
    ),
    non_regression_tolerance: float = 0.0,
    evaluator_refs: list[dict[str, Any]] | None = None,
) -> EvaluationResult:
    candidate_score = weighted_score(soft_scores, weights)
    baseline_score = weighted_score(baseline_scores, weights) if baseline_scores else None
    delta = round(candidate_score - baseline_score, 6) if baseline_score is not None else None
    negative_transfer = False
    if baseline_scores:
        negative_transfer = any(
            float(soft_scores[dimension]) + non_regression_tolerance
            < float(baseline_scores[dimension])
            for dimension in protected_dimensions
        )
    result = EvaluationResult(
        evaluation_id=stable_id(
            "eval",
            {
                "item": benchmark_item_id,
                "candidate": candidate_id,
                "split": split,
                "hard": hard_gates,
                "scores": soft_scores,
            },
        ),
        benchmark_item_id=benchmark_item_id,
        candidate_id=candidate_id,
        split=split,
        hard_gates=hard_gates,
        soft_scores=soft_scores,
        weighted_score=candidate_score,
        baseline_score=baseline_score,
        performance_delta=delta,
        negative_transfer=negative_transfer,
        evaluator_refs=evaluator_refs or [],
        notes=[] if all(hard_gates.values()) else ["Candidate failed a non-compensatory hard gate."],
    )
    result.validate()
    return result


def skillopt_reward(result: EvaluationResult) -> dict[str, Any]:
    result.validate()
    return {
        "hard": 1 if all(result.hard_gates.values()) and not result.negative_transfer else 0,
        "soft": result.weighted_score,
        "baseline_soft": result.baseline_score,
        "delta_soft": result.performance_delta,
        "extras": {
            "soft_scores": result.soft_scores,
            "hard_gates": result.hard_gates,
            "negative_transfer": result.negative_transfer,
            "evaluation_id": result.evaluation_id,
        },
    }


def transfer_report(results: Iterable[EvaluationResult]) -> dict[str, Any]:
    rows = list(results)
    if not rows:
        raise SchemaError("transfer report requires at least one evaluation")
    deltas = [row.performance_delta for row in rows if row.performance_delta is not None]
    successful = [
        row
        for row in rows
        if all(row.hard_gates.values())
        and not row.negative_transfer
        and (row.performance_delta is None or row.performance_delta >= 0)
    ]
    return {
        "schema_version": "assessment-transfer-report/1",
        "evaluation_count": len(rows),
        "hard_gate_pass_rate": sum(all(row.hard_gates.values()) for row in rows) / len(rows),
        "mean_performance_delta": mean(deltas) if deltas else None,
        "target_evolvability": len(successful) / len(rows),
        "negative_transfer_count": sum(row.negative_transfer for row in rows),
        "extraction_efficacy": (
            sum(row.soft_scores.get("evidence_grounding", 0) for row in rows) / len(rows)
        ),
        "evaluation_ids": [row.evaluation_id for row in rows],
    }
