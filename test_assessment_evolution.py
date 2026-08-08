"""Offline contract and workflow tests for assessment evolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assessment_evolution.artifacts import (
    ArtifactConflictError,
    ArtifactStore,
)
from assessment_evolution.compiler import compile_improvement_skill
from assessment_evolution.evaluation import (
    DEFAULT_WEIGHTS,
    evaluate_candidate,
    skillopt_reward,
    transfer_report,
)
from assessment_evolution.evidence import (
    aggregate_learner_confusion,
    build_evidence_bundle,
    extract_learner_candidates,
    extract_sme_candidates,
    review_evidence,
)
from assessment_evolution.evolution import (
    apply_patch,
    make_patch,
    no_change_result,
    validate_evolution,
    validate_target_contract,
)
from assessment_evolution.fixture_data import (
    TARGET_SKILL,
    benchmark_item,
    synthetic_learner_conversations,
    synthetic_sme_conversation,
    target_envelope,
)
from assessment_evolution.normalization import normalize_conversation
from assessment_evolution.pipeline import AssessmentEvolutionPipeline
from assessment_evolution.principles import (
    bank_metrics,
    create_bank,
    distill_sme_evidence,
    distill_learner_clusters,
    finalize_principle,
    select_bank,
)
from assessment_evolution.privacy import (
    classify_learner_span,
    detect_privacy,
    sanitize_conversation,
)
from assessment_evolution.schemas import (
    AssessmentImprovementPrinciple,
    ConversationRecord,
    EvidenceReview,
    EvolutionResult,
    LearnerConfusionEvidence,
    SMEEvidence,
    SchemaError,
    content_hash,
)


class SchemaTests(unittest.TestCase):
    def test_unknown_fields_are_rejected(self) -> None:
        raw = synthetic_sme_conversation().to_dict()
        raw["unexpected"] = True
        with self.assertRaises(SchemaError):
            ConversationRecord.from_dict(raw)

    def test_normalization_is_stable(self) -> None:
        kwargs = {
            "source": "fixture",
            "source_conversation_id": "stable",
            "messages": [{"role": "human", "content": "Use a scenario."}],
            "persona": "sme",
            "participant_ids": ["one"],
            "consent": {
                "assessment_improvement": True,
                "llm_processing": False,
                "telemetry_redacted": False,
            },
        }
        left = normalize_conversation(**kwargs)
        right = normalize_conversation(**kwargs)
        self.assertEqual(left.conversation_id, right.conversation_id)
        self.assertEqual(left.messages[0]["message_id"], right.messages[0]["message_id"])

    def test_benchmark_fixture_validates(self) -> None:
        item = benchmark_item("train", 1)
        self.assertEqual(item.split, "train")
        self.assertTrue(item.metadata["synthetic_fixture"])


class PrivacyTests(unittest.TestCase):
    def test_secret_and_pii_are_redacted(self) -> None:
        record = normalize_conversation(
            source="fixture",
            source_conversation_id="pii",
            messages=[
                {
                    "role": "user",
                    "content": "Email me at a@example.com; api_key=abcdefghijk12345",
                }
            ],
            persona="sme",
            consent={
                "assessment_improvement": True,
                "llm_processing": True,
                "telemetry_redacted": True,
            },
        )
        sanitized, report = sanitize_conversation(record)
        self.assertIn("[REDACTED_EMAIL]", sanitized.messages[0]["content"])
        self.assertIn("[REDACTED_CREDENTIAL]", sanitized.messages[0]["content"])
        self.assertEqual(len(detect_privacy(sanitized.messages[0]["content"])), 0)
        self.assertEqual(len(report.detections), 2)

    def test_learner_solution_is_not_an_understanding_signal(self) -> None:
        boundary, category, labels = classify_learner_span(
            "What does output mean and give me the answer?"
        )
        self.assertEqual(boundary, "mixed")
        self.assertIsNotNone(category)
        self.assertIn("learner.hint_request", labels)

    def test_only_comprehension_candidates_survive(self) -> None:
        allowed = synthetic_learner_conversations()[0]
        candidates = extract_learner_candidates(allowed)
        self.assertEqual(len(candidates), 1)
        blocked = normalize_conversation(
            source="fixture",
            source_conversation_id="solution",
            messages=[{"role": "user", "content": "Show me the answer and command to solve this."}],
            persona="learner",
            participant_ids=["learner"],
            consent={
                "assessment_improvement": True,
                "llm_processing": True,
                "telemetry_redacted": True,
            },
        )
        self.assertEqual(extract_learner_candidates(blocked), [])

    def test_sanitized_mixed_learner_conversation_is_quarantined(self) -> None:
        record = normalize_conversation(
            source="fixture",
            source_conversation_id="mixed",
            messages=[
                {
                    "role": "user",
                    "content": "The output instruction is unclear; show me the answer.",
                }
            ],
            persona="learner",
            participant_ids=["learner"],
            consent={
                "assessment_improvement": True,
                "llm_processing": True,
                "telemetry_redacted": True,
            },
        )
        sanitized, report = sanitize_conversation(record)
        self.assertFalse(report.optimizer_allowed)
        self.assertEqual(sanitized.metadata["solution_boundary"], "quarantined")


class EvidenceTests(unittest.TestCase):
    def test_review_is_immutable_and_required(self) -> None:
        candidate = extract_sme_candidates(synthetic_sme_conversation())[0]
        review = EvidenceReview(
            review_id="review_1",
            evidence_id=candidate.evidence_id,
            decision="approved",
            reviewer_id="sme_reviewer",
            reviewer_role="sme",
            reason_codes=["source_matches"],
        )
        approved = review_evidence(candidate, review)
        self.assertEqual(candidate.review_status, "pending")
        self.assertEqual(approved.review_status, "approved")

    def test_learner_cluster_needs_three_distinct_people(self) -> None:
        candidates = [
            extract_learner_candidates(record)[0]
            for record in synthetic_learner_conversations()
        ]
        clusters, excluded = aggregate_learner_confusion(candidates)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["distinct_learner_count"], 3)
        self.assertEqual(excluded, [])
        clusters, excluded = aggregate_learner_confusion(candidates[:2])
        self.assertEqual(clusters, [])
        self.assertEqual(len(excluded), 2)

    def test_bundle_fails_closed_on_pending_evidence(self) -> None:
        candidate = extract_sme_candidates(synthetic_sme_conversation())[0]
        with self.assertRaises(SchemaError):
            build_evidence_bundle(
                domain_profile_id="fixture",
                target_scope=["fixture-*"],
                sme_evidence=[candidate],
                learner_clusters=[],
                split_manifest="split",
                review_manifest="review",
            )


class ArtifactTests(unittest.TestCase):
    def test_immutable_write_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ArtifactStore(Path(temp), "run_test")
            first = store.put_text(
                stage="input",
                name="value.txt",
                text="one",
                artifact_type="fixture",
                created_by="test",
            )
            second = store.put_text(
                stage="input",
                name="value.txt",
                text="one",
                artifact_type="fixture",
                created_by="test",
            )
            self.assertEqual(first.artifact_id, second.artifact_id)
            with self.assertRaises(ArtifactConflictError):
                store.put_text(
                    stage="input",
                    name="value.txt",
                    text="two",
                    artifact_type="fixture",
                    created_by="test",
                )
            self.assertEqual(store.verify(), [])

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ArtifactStore(Path(temp), "run_test")
            with self.assertRaises(ValueError):
                store.put_text(
                    stage="input",
                    name="../escape.txt",
                    text="bad",
                    artifact_type="fixture",
                    created_by="test",
                )


class PrincipleAndCompilerTests(unittest.TestCase):
    def _approved_evidence(self) -> list[SMEEvidence]:
        candidates = extract_sme_candidates(synthetic_sme_conversation())
        for candidate in candidates:
            candidate.review_status = "approved"
        return candidates

    def test_distill_bank_select_and_compile(self) -> None:
        evidence = self._approved_evidence()
        principles = distill_sme_evidence(evidence)
        for principle in principles:
            principle.review_status = "approved"
            finalize_principle(principle)
        expected = [item.evidence_id for item in evidence]
        metrics = bank_metrics(
            principles, expected_evidence_ids=expected, measured_utility=0.75
        )
        bank = create_bank(
            principles=principles,
            evidence_bundle_id="bundle_test",
            proposal_id="proposal_test",
            objectives=metrics,
            operations=[],
            hard_gates_passed=True,
        )
        selected = select_bank([bank])
        compiled = compile_improvement_skill(selected)
        self.assertIn("## Optimized Evidence-Backed Principles", compiled.skill_markdown)
        self.assertEqual(
            compiled.manifest["compiled_hash"], content_hash(compiled.skill_markdown)
        )

    def test_bank_without_hard_gate_cannot_be_selected(self) -> None:
        with self.assertRaises(SchemaError):
            select_bank([])

    def test_approved_learner_cluster_becomes_bounded_principle(self) -> None:
        candidates = [
            extract_learner_candidates(record)[0]
            for record in synthetic_learner_conversations()
        ]
        clusters, _ = aggregate_learner_confusion(candidates)
        clusters[0]["review_status"] = "approved"
        principles = distill_learner_clusters(clusters)
        self.assertEqual(principles[0].learner_cluster_ids, [clusters[0]["cluster_id"]])
        self.assertTrue(
            any("Do not add commands" in rule for rule in principles[0].high_risk_blacklist)
        )


class EvolutionTests(unittest.TestCase):
    def test_patch_reconstructs_exact_output(self) -> None:
        original = TARGET_SKILL
        evolved = original.replace(
            "3. State the task without providing its answer.",
            "3. State the observable output without providing its answer.",
        )
        patch = make_patch(
            original,
            evolved,
            evidence_ids=["sme_ev_1"],
            rationale="Approved SME correction.",
            expected_effect="Clarifies completion.",
        )
        self.assertEqual(apply_patch(original, patch), evolved)

    def test_immutable_section_regression_is_blocked(self) -> None:
        envelope = target_envelope()
        evolved = TARGET_SKILL.replace("Do not reveal answers", "Reveal answers")
        gates = validate_target_contract(envelope, evolved)
        self.assertFalse(gates["immutable_sections_preserved"])

    def test_no_change_result_passes_contract(self) -> None:
        envelope = target_envelope()
        result = no_change_result(
            envelope,
            evidence_ids=["sme_ev_1"],
            summary="The current target already states the approved behavior.",
        )
        gates = validate_evolution(
            result, envelope, approved_evidence_ids=["sme_ev_1"]
        )
        self.assertTrue(gates["patch_reconstructs_output"])
        self.assertTrue(gates["immutable_sections_preserved"])

    def test_model_style_anchored_patch_reconstructs(self) -> None:
        before = "3. State the task without providing its answer."
        after = "3. State the observable output without providing its answer."
        operation = {
            "operation_id": "op_001",
            "operation": "replace",
            "target": {"section": "Workflow", "anchor": "## Workflow"},
            "before_hash": content_hash(before),
            "after_hash": content_hash(after),
            "before": before,
            "after": after,
            "rationale": "Approved correction",
            "evidence_ids": ["sme_ev_1"],
            "principle_ids": [],
            "expected_effect": "Clear output",
            "risk": "low",
            "reversible": True,
        }
        self.assertEqual(
            apply_patch(TARGET_SKILL, [operation]),
            TARGET_SKILL.replace(before, after),
        )


class EvaluationTests(unittest.TestCase):
    def test_negative_transfer_zeroes_hard_reward(self) -> None:
        baseline = {name: 0.8 for name in DEFAULT_WEIGHTS}
        candidate = dict(baseline)
        candidate["difficulty_calibration"] = 0.5
        result = evaluate_candidate(
            benchmark_item_id="item",
            candidate_id="candidate",
            split="validation",
            hard_gates={"schema": True},
            soft_scores=candidate,
            baseline_scores=baseline,
        )
        self.assertTrue(result.negative_transfer)
        self.assertEqual(skillopt_reward(result)["hard"], 0)
        report = transfer_report([result])
        self.assertEqual(report["negative_transfer_count"], 1)


class OfflinePipelineTests(unittest.TestCase):
    def test_governed_pipeline_to_compiled_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ArtifactStore(Path(temp), "run_e2e")
            conversations = [
                synthetic_sme_conversation(),
                *synthetic_learner_conversations(),
            ]
            for record in conversations:
                store.put_json(
                    stage="normalized",
                    name=f"{record.conversation_id}.json",
                    value=record.to_dict(),
                    artifact_type="canonical-conversation",
                    created_by="test",
                    sensitivity="restricted",
                )
            pipeline = AssessmentEvolutionPipeline(store)
            self.assertEqual(len(pipeline.sanitize()), 4)
            pipeline.extract_evidence()
            self.assertEqual(pipeline.extract_evidence(), [])
            candidates = [
                (manifest, raw)
                for artifact_type in ("sme-evidence-candidate", "learner-evidence-candidate")
                for manifest, raw in pipeline._json_artifacts(artifact_type)
            ]
            self.assertGreaterEqual(len(candidates), 4)
            for _, raw in candidates:
                pipeline.review_candidate(
                    evidence_id=raw["evidence_id"],
                    decision="approved",
                    reviewer_id="fixture-reviewer",
                    reviewer_role="sme",
                    reason_codes=["synthetic_fixture_verified"],
                )
            pipeline.aggregate_learners()
            cluster = pipeline._json_artifacts("learner-confusion-cluster")[0][1]
            pipeline.review_cluster(
                cluster_id=cluster["cluster_id"],
                decision="approved",
                reviewer_id="fixture-sme",
            )
            pipeline.build_bundle(
                domain_profile_id="fixture-domain:v1",
                target_scope=["fixture-*"],
                split_manifest="fixture-splits:v1",
            )
            pipeline.distill_principles()
            for _, raw in pipeline._json_artifacts("principle-candidate"):
                pipeline.review_principle(
                    principle_id=raw["principle_id"],
                    decision="approved",
                    reviewer_id="fixture-reviewer",
                    reviewer_role="sme",
                )
            bundle = pipeline._json_artifacts("evidence-bundle")[0][1]
            pipeline.curate_bank(
                evidence_bundle_id=bundle["bundle_id"], measured_utility=0.7
            )
            bank = pipeline._json_artifacts("selected-principle-bank")[0][1]
            pipeline.compile_skill(bank_id=bank["bank_id"])
            compiled = pipeline._latest_text("compiled-improvement-skill")
            self.assertIn("Optimized Evidence-Backed Principles", compiled)
            self.assertEqual(store.verify(), [])

    def test_release_stays_proposal_only_after_sme_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ArtifactStore(Path(temp), "run_release")
            pipeline = AssessmentEvolutionPipeline(store)
            pipeline.prepare_release(
                evolution_result_id="artifact_evolution",
                target_skill_id="fixture-target",
                prior_version="v1",
                proposed_version="v2",
                evaluation_ids=["eval_1"],
                rollback={"previous_version": "v1"},
            )
            proposal = pipeline._json_artifacts("release-proposal")[0][1]
            pipeline.review_release(
                release_id=proposal["release_id"],
                decision="approved",
                reviewer_id="fixture-sme",
                reviewer_role="sme",
            )
            reviewed = pipeline._json_artifacts("reviewed-release-proposal")[0][1]
            self.assertEqual(reviewed["status"], "approved")
            manifest = store.artifacts()[-1]
            self.assertFalse(manifest.metadata["promotion_performed"])


class SkillOptContractTests(unittest.TestCase):
    def test_actual_adapter_loads_all_fixture_splits(self) -> None:
        try:
            from assessment_evolution.skillopt_env import (
                AssessmentImproverAdapter,
                SKILLOPT_AVAILABLE,
            )
        except ImportError:
            self.skipTest("SkillOpt adapter is unavailable")
        if not SKILLOPT_AVAILABLE:
            self.skipTest("SkillOpt is not installed")
        adapter = AssessmentImproverAdapter(
            split_dir="fixtures/assessment_improver",
            split_mode="split_dir",
        )
        adapter.setup({})
        self.assertEqual(
            (
                len(adapter.dataloader.train_items),
                len(adapter.dataloader.val_items),
                len(adapter.dataloader.test_items),
            ),
            (3, 2, 2),
        )

    def test_failed_rollout_still_persists_reflection_trajectory(self) -> None:
        try:
            from assessment_evolution.skillopt_env.rollout import run_batch
        except ImportError:
            self.skipTest("SkillOpt rollout is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            result = run_batch(
                items=[{"id": "invalid_fixture", "task_type": "contract"}],
                skill_content="# Candidate",
                out_root=temp,
            )
            self.assertEqual(result[0]["hard"], 0)
            self.assertTrue(
                (Path(temp) / "predictions" / "invalid_fixture" / "conversation.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
