"""Two-stage target evolution and paired assessment-generation rollout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..evaluation import DEFAULT_WEIGHTS, evaluate_candidate, skillopt_reward
from ..evolution import evolution_from_model
from ..privacy import detect_privacy
from ..schemas import BenchmarkItem, EvolutionResult, TargetSkillEnvelope, content_hash


def _chat(*, system: str, user: str, max_completion_tokens: int) -> str:
    try:
        from skillopt.model import chat_target
    except ImportError as exc:
        raise RuntimeError("SkillOpt 0.2.0 is required for rollouts") from exc
    output, _usage = chat_target(
        system=system,
        user=user,
        max_completion_tokens=max_completion_tokens,
    )
    return output


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("evolution output must be one JSON object")
    return value


def _assessment_hard_gates(text: str, brief: dict[str, Any]) -> dict[str, bool]:
    required = [str(value) for value in brief.get("required_literals") or []]
    prohibited = [str(value) for value in brief.get("prohibited_literals") or []]
    return {
        "assessment_nonempty": bool(text.strip()),
        "assessment_required_content": all(value in text for value in required),
        "assessment_prohibited_content_absent": not any(value in text for value in prohibited),
        "assessment_secret_free": not bool(detect_privacy(text)),
        "assessment_minimum_length": len(text.strip()) >= int(brief.get("minimum_characters", 1)),
    }


def _dimension_scores(
    text: str,
    item: BenchmarkItem,
    *,
    compatibility: float,
    evidence_grounding: float,
    minimality: float,
) -> dict[str, float]:
    scores = {name: 0.5 for name in DEFAULT_WEIGHTS}
    for behavior in item.expected_behaviors:
        dimension = str(behavior.get("dimension") or "")
        if dimension not in scores:
            continue
        required = [str(value).lower() for value in behavior.get("required_phrases") or []]
        prohibited = [str(value).lower() for value in behavior.get("prohibited_phrases") or []]
        lowered = text.lower()
        checks = [value in lowered for value in required] + [
            value not in lowered for value in prohibited
        ]
        scores[dimension] = sum(checks) / len(checks) if checks else float(
            behavior.get("default_score", 0.5)
        )
    scores["target_compatibility"] = compatibility
    scores["evidence_grounding"] = evidence_grounding
    scores["minimality"] = minimality
    return scores


def _rollout_one(
    item_raw: dict[str, Any],
    skill_content: str,
    *,
    prediction_dir: Path,
    max_completion_tokens: int,
) -> dict[str, Any]:
    item = BenchmarkItem.from_dict(
        {key: value for key, value in item_raw.items() if key != "task_type"}
    )
    envelope = TargetSkillEnvelope.from_dict(item.target_skill_envelope)
    approved_items = item.evidence_bundle.get("items") or []
    approved_ids = {
        str(row.get("evidence_id") or row.get("cluster_id"))
        for row in approved_items
        if row.get("review_status") in {"approved", "approved_with_edits"}
    }
    evolution_user = json.dumps(
        {
            "target_skill_envelope": item.target_skill_envelope,
            "domain_profile": item.domain_profile,
            "approved_evidence": approved_items,
            "constraints": {
                "return_schema": EvolutionResult.SCHEMA,
                "assessment_brief": item.assessment_brief,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    evolution_text = _chat(
        system=skill_content,
        user=evolution_user,
        max_completion_tokens=max_completion_tokens,
    )
    result, evolution_gates = evolution_from_model(
        _json_object(evolution_text),
        envelope=envelope,
        approved_evidence_ids=approved_ids,
    )
    critical_evolution_pass = all(
        value
        for name, value in evolution_gates.items()
        if not name.endswith("_detected")
    ) and not any(
        value for name, value in evolution_gates.items() if name.endswith("_detected")
    )
    brief_text = json.dumps(item.assessment_brief, ensure_ascii=False, sort_keys=True)
    baseline_assessment = _chat(
        system=envelope.exact_skill_markdown,
        user=brief_text,
        max_completion_tokens=max_completion_tokens,
    )
    candidate_assessment = ""
    if critical_evolution_pass and result.decision != "needs_review":
        candidate_assessment = _chat(
            system=result.evolved_skill_markdown,
            user=brief_text,
            max_completion_tokens=max_completion_tokens,
        )
    baseline_hard = _assessment_hard_gates(baseline_assessment, item.assessment_brief)
    candidate_hard = _assessment_hard_gates(candidate_assessment, item.assessment_brief)
    hard_gates = {
        **{f"evolution.{key}": value for key, value in evolution_gates.items() if not key.endswith("_detected")},
        "evolution.solution_free": not evolution_gates.get("learner_solution_leakage_detected", False),
        "evolution.privacy_safe": not evolution_gates.get("privacy_leakage_detected", False),
        **{f"assessment.{key}": value for key, value in candidate_hard.items()},
    }
    changed_lines = sum(
        len(str(operation.get("after") or "").splitlines())
        + len(str(operation.get("before") or "").splitlines())
        for operation in result.patch
    )
    total_lines = max(1, len(envelope.exact_skill_markdown.splitlines()))
    minimality = max(0.0, 1 - changed_lines / total_lines)
    evidence_grounding = 1.0 if all(
        operation.get("evidence_ids") for operation in result.patch
    ) else (1.0 if not result.patch else 0.0)
    baseline_scores = _dimension_scores(
        baseline_assessment,
        item,
        compatibility=1.0 if all(baseline_hard.values()) else 0.0,
        evidence_grounding=0.5,
        minimality=1.0,
    )
    candidate_scores = _dimension_scores(
        candidate_assessment,
        item,
        compatibility=1.0 if all(candidate_hard.values()) and critical_evolution_pass else 0.0,
        evidence_grounding=evidence_grounding,
        minimality=minimality,
    )
    evaluation = evaluate_candidate(
        benchmark_item_id=item.id,
        candidate_id=content_hash(skill_content),
        split=item.split,
        hard_gates=hard_gates,
        soft_scores=candidate_scores,
        baseline_scores=baseline_scores,
    )
    reward = skillopt_reward(evaluation)
    task_dir = prediction_dir / item.id
    task_dir.mkdir(parents=True, exist_ok=True)
    conversation = [
        {"role": "system", "content": skill_content},
        {"role": "user", "content": evolution_user},
        {"role": "assistant", "content": evolution_text},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "deterministic_evolution_gates": evolution_gates,
                    "baseline_assessment": baseline_assessment,
                    "candidate_assessment": candidate_assessment,
                    "evaluation": evaluation.to_dict(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]
    (task_dir / "conversation.json").write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (task_dir / "evolution-result.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (task_dir / "baseline-assessment.txt").write_text(
        baseline_assessment, encoding="utf-8"
    )
    (task_dir / "candidate-assessment.txt").write_text(
        candidate_assessment, encoding="utf-8"
    )
    return {
        "id": item.id,
        "hard": reward["hard"],
        "soft": reward["soft"],
        "baseline_soft": reward["baseline_soft"],
        "delta_soft": reward["delta_soft"],
        "task_type": item_raw.get("task_type", "assessment-evolution"),
        "task_description": json.dumps(item.assessment_brief, ensure_ascii=False),
        "target_system_prompt": skill_content,
        "target_user_prompt": evolution_user,
        "predicted_answer": evolution_text,
        "n_turns": 2,
        "evaluation": evaluation.to_dict(),
        "evolution_result": result.to_dict(),
    }


def run_batch(
    *,
    items: list[dict[str, Any]],
    skill_content: str,
    out_root: str,
    workers: int = 1,
    max_completion_tokens: int = 8192,
) -> list[dict[str, Any]]:
    # Sequential execution keeps paired baseline/candidate requests ordered and
    # reproducible. SkillOpt can parallelize batches at the trainer level.
    del workers
    root = Path(out_root)
    prediction_dir = root / "predictions"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in items:
        try:
            results.append(
                _rollout_one(
                    item,
                    skill_content,
                    prediction_dir=prediction_dir,
                    max_completion_tokens=max_completion_tokens,
                )
            )
        except Exception as exc:
            item_id = str(item.get("id") or "unknown")
            task_dir = prediction_dir / item_id
            task_dir.mkdir(parents=True, exist_ok=True)
            failure = {
                "id": item_id,
                "hard": 0,
                "soft": 0.0,
                "fail_reason": f"{type(exc).__name__}: {exc}",
                "task_type": item.get("task_type", "assessment-evolution"),
                "task_description": json.dumps(
                    item.get("assessment_brief") or {}, ensure_ascii=False
                ),
                "target_system_prompt": skill_content,
                "target_user_prompt": json.dumps(item, ensure_ascii=False, sort_keys=True),
                "predicted_answer": "",
                "n_turns": 1,
            }
            conversation = [
                {"role": "system", "content": skill_content},
                {
                    "role": "user",
                    "content": json.dumps(item, ensure_ascii=False, sort_keys=True),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "rollout_failure": failure["fail_reason"],
                            "hard": 0,
                            "soft": 0.0,
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            (task_dir / "conversation.json").write_text(
                json.dumps(conversation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (task_dir / "failure.json").write_text(
                json.dumps(failure, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results.append(failure)
    (root / "rollouts.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results
