"""Resumable orchestration over the immutable artifact store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .artifacts import ArtifactStore
from .compiler import CompilationResult, compile_improvement_skill
from .evidence import (
    aggregate_learner_confusion,
    build_evidence_bundle,
    extract_learner_candidates,
    extract_sme_candidates,
    review_evidence,
    sme_candidates_from_model,
)
from .evolution import evolution_from_model
from .llm import ModelSettings, StructuredModelClient
from .normalization import (
    normalize_capture_store,
    normalize_conversation_markdown,
    render_markdown,
)
from .observability import Observability
from .principles import (
    bank_metrics,
    create_bank,
    distill_learner_clusters,
    distill_sme_evidence,
    finalize_principle,
    select_bank,
)
from .privacy import sanitize_conversation
from .prompts import Prompt, load_prompt
from .schemas import (
    AssessmentImprovementPrinciple,
    ConversationRecord,
    DomainProfile,
    EvidenceBundle,
    EvidenceReview,
    EvolutionResult,
    LearnerConfusionEvidence,
    PrincipleBankVersion,
    ReleaseProposal,
    SMEEvidence,
    SchemaError,
    TargetSkillEnvelope,
    content_hash,
    stable_id,
    utc_now,
)


class AssessmentEvolutionPipeline:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self.observability = Observability(
            run_id=store.run_id,
            queue_path=store.run_dir / "telemetry.pending.jsonl",
            required=False,
        )

    def ingest(
        self,
        path: Path,
        *,
        source: str,
        persona: str,
        consent: dict[str, bool],
        retention_class: str,
    ) -> list[str]:
        if source == "local":
            records = normalize_capture_store(
                path,
                persona=persona,
                consent=consent,
                retention_class=retention_class,
            )
        elif source in {"langsmith-markdown", "markdown", "learner-markdown"}:
            paths = sorted(path.glob("*.md")) if path.is_dir() else [path]
            records = [
                normalize_conversation_markdown(
                    item,
                    persona=persona,
                    consent=consent,
                    retention_class=retention_class,
                )
                for item in paths
            ]
        elif source == "canonical":
            paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
            records = [
                ConversationRecord.from_dict(json.loads(item.read_text(encoding="utf-8")))
                for item in paths
            ]
        else:
            raise ValueError(f"unsupported ingestion source {source!r}")
        artifact_ids = []
        for record in records:
            with self.observability.span(
                "conversation.normalize",
                metadata={
                    "conversation_id": record.conversation_id,
                    "persona": record.persona,
                    "stage": "ingestion",
                },
            ):
                manifest = self.store.put_json(
                    stage="normalized",
                    name=f"{record.conversation_id}.json",
                    value=record.to_dict(),
                    artifact_type="canonical-conversation",
                    created_by="assessment-evolution-normalizer:v1",
                    source_record_ids=[record.source_conversation_id],
                    validator_refs=["assessment-conversation:v1"],
                    sensitivity="restricted",
                    metadata={"persona": record.persona, "source": record.source},
                )
                self.store.put_text(
                    stage="normalized",
                    name=f"{record.conversation_id}.md",
                    text=render_markdown(record),
                    artifact_type="canonical-conversation-view",
                    created_by="assessment-evolution-normalizer:v1",
                    parent_artifact_ids=[manifest.artifact_id],
                    source_record_ids=[record.source_conversation_id],
                    sensitivity="restricted",
                )
                artifact_ids.append(manifest.artifact_id)
        return artifact_ids

    def sanitize(self) -> list[str]:
        outputs = []
        for manifest, raw in self._json_artifacts("canonical-conversation"):
            record = ConversationRecord.from_dict(raw)
            with self.observability.span(
                "conversation.redact",
                metadata={
                    "conversation_id": record.conversation_id,
                    "persona": record.persona,
                    "stage": "sanitization",
                },
            ):
                sanitized, report = sanitize_conversation(record)
                sanitized_manifest = self.store.put_json(
                    stage="sanitized",
                    name=f"{record.conversation_id}.json",
                    value=sanitized.to_dict(),
                    artifact_type="sanitized-conversation",
                    created_by="assessment-evolution-redactor:v1",
                    parent_artifact_ids=[manifest.artifact_id],
                    source_record_ids=[record.conversation_id],
                    validator_refs=["redaction-policy:v1", "assessment-conversation:v1"],
                    sensitivity="sanitized",
                    metadata={"persona": record.persona},
                )
                self.store.put_json(
                    stage="sanitized",
                    name=f"{report.report_id}.json",
                    value=report.to_dict(),
                    artifact_type="redaction-report",
                    created_by="assessment-evolution-redactor:v1",
                    parent_artifact_ids=[manifest.artifact_id, sanitized_manifest.artifact_id],
                    source_record_ids=[record.conversation_id],
                    validator_refs=["redaction-policy:v1"],
                    sensitivity="sanitized",
                )
                outputs.append(sanitized_manifest.artifact_id)
        return outputs

    def extract_evidence(self, *, use_model: bool = False) -> list[str]:
        outputs = []
        client = (
            StructuredModelClient(
                ModelSettings.from_env(), observability=self.observability
            )
            if use_model
            else None
        )
        prompt = load_prompt("sme-evidence-extractor") if client else None
        completed_conversations = {
            source_id
            for artifact in self.store.artifacts()
            if artifact.artifact_type == "evidence-extraction-report"
            for source_id in artifact.source_record_ids
        }
        for manifest, raw in self._json_artifacts("sanitized-conversation"):
            record = ConversationRecord.from_dict(raw)
            if record.conversation_id in completed_conversations:
                continue
            if not record.consent.get("assessment_improvement"):
                continue
            if record.persona == "learner" and not record.metadata.get("optimizer_allowed", True):
                self.store.put_json(
                    stage="evidence_candidates",
                    name=f"{record.conversation_id}.extraction.json",
                    value={
                        "schema_version": "evidence-extraction-report/1",
                        "conversation_id": record.conversation_id,
                        "persona": record.persona,
                        "candidate_count": 0,
                        "status": "quarantined",
                        "reason": "learner_solution_boundary",
                    },
                    artifact_type="evidence-extraction-report",
                    created_by="assessment-evolution-evidence:v1",
                    parent_artifact_ids=[manifest.artifact_id],
                    source_record_ids=[record.conversation_id],
                    sensitivity="sanitized",
                )
                continue
            if record.persona == "sme":
                candidates: list[SMEEvidence]
                model_ref: dict[str, Any] | None = None
                if client and prompt and record.consent.get("llm_processing"):
                    response, model_ref = client.generate_json(
                        prompt=prompt,
                        user_payload={
                            "conversation": {
                                "conversation_id": record.conversation_id,
                                "domain": record.domain,
                                "assessment_id": record.assessment_id,
                                "messages": record.messages,
                            }
                        },
                        observation_name="evidence.sme.extract",
                        parent_artifact_ids=[manifest.artifact_id],
                    )
                    candidates = sme_candidates_from_model(
                        record, response.get("items") or [], model_ref=model_ref
                    )
                else:
                    candidates = extract_sme_candidates(record)
                artifact_type = "sme-evidence-candidate"
            elif record.persona == "learner":
                candidates = extract_learner_candidates(record)
                artifact_type = "learner-evidence-candidate"
                model_ref = None
            else:
                continue
            for candidate in candidates:
                candidate_manifest = self.store.put_json(
                    stage="evidence_candidates",
                    name=f"{candidate.evidence_id}.json",
                    value=candidate.to_dict(),
                    artifact_type=artifact_type,
                    created_by="assessment-evolution-evidence:v1",
                    parent_artifact_ids=[manifest.artifact_id],
                    source_record_ids=[record.conversation_id],
                    prompt_refs=(
                        [
                            {
                                "name": prompt.name,
                                "git_hash": prompt.git_hash,
                            }
                        ]
                        if prompt and model_ref
                        else []
                    ),
                    model_refs=[model_ref] if model_ref else [],
                    validator_refs=[candidate.schema_version],
                    sensitivity="sanitized",
                    metadata={"persona": record.persona},
                )
                outputs.append(candidate_manifest.artifact_id)
            self.store.put_json(
                stage="evidence_candidates",
                name=f"{record.conversation_id}.extraction.json",
                value={
                    "schema_version": "evidence-extraction-report/1",
                    "conversation_id": record.conversation_id,
                    "persona": record.persona,
                    "candidate_count": len(candidates),
                    "status": "complete",
                    "reason": None,
                },
                artifact_type="evidence-extraction-report",
                created_by="assessment-evolution-evidence:v1",
                parent_artifact_ids=[manifest.artifact_id],
                source_record_ids=[record.conversation_id],
                sensitivity="sanitized",
            )
        self.observability.flush()
        return outputs

    def review_candidate(
        self,
        *,
        evidence_id: str,
        decision: str,
        reviewer_id: str,
        reviewer_role: str,
        reason_codes: list[str],
        comment: str | None = None,
        field_corrections: dict[str, Any] | None = None,
    ) -> str:
        manifest, raw = self._find_evidence(evidence_id)
        evidence = (
            SMEEvidence.from_dict(raw)
            if raw.get("schema_version") == SMEEvidence.SCHEMA
            else LearnerConfusionEvidence.from_dict(raw)
        )
        if (
            isinstance(evidence, SMEEvidence)
            and decision in {"approved", "approved_with_edits"}
            and reviewer_role != "sme"
        ):
            raise SchemaError("SME evidence approval requires reviewer_role=sme")
        review = EvidenceReview(
            review_id=stable_id(
                "review",
                {
                    "evidence_id": evidence_id,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "time": utc_now(),
                },
            ),
            evidence_id=evidence_id,
            decision=decision,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            reason_codes=reason_codes,
            comment=comment,
            field_corrections=field_corrections or {},
        )
        reviewed = review_evidence(evidence, review)
        review_manifest = self.store.put_json(
            stage="approved_evidence",
            name=f"{review.review_id}.json",
            value=review.to_dict(),
            artifact_type="evidence-review",
            created_by="assessment-evolution-review:v1",
            parent_artifact_ids=[manifest.artifact_id],
            source_record_ids=[evidence_id],
            sensitivity="sanitized",
            metadata={"decision": decision, "reviewer_role": reviewer_role},
        )
        reviewed_manifest = self.store.put_json(
            stage="approved_evidence",
            name=f"{evidence_id}.{review.review_id}.json",
            value=reviewed.to_dict(),
            artifact_type="reviewed-sme-evidence"
            if isinstance(reviewed, SMEEvidence)
            else "reviewed-learner-evidence",
            created_by="assessment-evolution-review:v1",
            parent_artifact_ids=[manifest.artifact_id, review_manifest.artifact_id],
            source_record_ids=[evidence_id],
            validator_refs=[reviewed.schema_version, review.schema_version],
            sensitivity="sanitized",
            metadata={"review_status": reviewed.review_status},
        )
        return reviewed_manifest.artifact_id

    def aggregate_learners(self, *, minimum_distinct_learners: int = 3) -> list[str]:
        items = [
            LearnerConfusionEvidence.from_dict(raw)
            for _, raw in self._json_artifacts(
                "reviewed-learner-evidence", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        clusters, excluded = aggregate_learner_confusion(
            items, minimum_distinct_learners=minimum_distinct_learners
        )
        outputs = []
        for cluster in clusters:
            manifest = self.store.put_json(
                stage="approved_evidence",
                name=f"{cluster['cluster_id']}.json",
                value=cluster,
                artifact_type="learner-confusion-cluster",
                created_by="assessment-evolution-learner-aggregator:v1",
                source_record_ids=cluster["evidence_ids"],
                validator_refs=["learner-confusion-cluster:v1"],
                sensitivity="sanitized",
            )
            outputs.append(manifest.artifact_id)
        if excluded:
            self.store.put_json(
                stage="approved_evidence",
                name="learner-aggregation-exclusions.json",
                value={"schema_version": "learner-aggregation-exclusions/1", "items": excluded},
                artifact_type="learner-aggregation-exclusions",
                created_by="assessment-evolution-learner-aggregator:v1",
                sensitivity="sanitized",
            )
        return outputs

    def review_cluster(
        self,
        *,
        cluster_id: str,
        decision: str,
        reviewer_id: str,
        comment: str | None = None,
    ) -> str:
        manifest, raw = self._find_json_by_id("learner-confusion-cluster", "cluster_id", cluster_id)
        if decision not in {"approved", "approved_with_edits", "rejected", "deferred"}:
            raise SchemaError("invalid learner-cluster review decision")
        reviewed = {**raw, "review_status": decision}
        review_id = stable_id(
            "review",
            {
                "cluster_id": cluster_id,
                "reviewer_id": reviewer_id,
                "decision": decision,
                "time": utc_now(),
            },
        )
        reviewed["review"] = {
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "reviewer_role": "sme",
            "decision": decision,
            "comment": comment,
            "reviewed_at": utc_now(),
        }
        output = self.store.put_json(
            stage="approved_evidence",
            name=f"{cluster_id}.{review_id}.json",
            value=reviewed,
            artifact_type="reviewed-learner-confusion-cluster",
            created_by="assessment-evolution-review:v1",
            parent_artifact_ids=[manifest.artifact_id],
            source_record_ids=[cluster_id, *raw["evidence_ids"]],
            sensitivity="sanitized",
        )
        return output.artifact_id

    def build_bundle(
        self,
        *,
        domain_profile_id: str,
        target_scope: list[str],
        split_manifest: str,
    ) -> str:
        sme = [
            SMEEvidence.from_dict(raw)
            for _, raw in self._json_artifacts(
                "reviewed-sme-evidence", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        clusters = [
            raw
            for _, raw in self._json_artifacts(
                "reviewed-learner-confusion-cluster", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        review_ids = [
            manifest.artifact_id
            for manifest in self.store.artifacts()
            if manifest.artifact_type == "evidence-review"
        ]
        bundle = build_evidence_bundle(
            domain_profile_id=domain_profile_id,
            target_scope=target_scope,
            sme_evidence=sme,
            learner_clusters=clusters,
            split_manifest=split_manifest,
            review_manifest=content_hash(review_ids),
        )
        manifest = self.store.put_json(
            stage="approved_evidence",
            name=f"{bundle.bundle_id}.json",
            value=bundle.to_dict(),
            artifact_type="evidence-bundle",
            created_by="assessment-evolution-bundle-builder:v1",
            source_record_ids=[*bundle.sme_evidence_ids, *bundle.learner_cluster_ids],
            validator_refs=[bundle.schema_version],
            sensitivity="sanitized",
        )
        return manifest.artifact_id

    def distill_principles(self) -> list[str]:
        approved_sme = [
            SMEEvidence.from_dict(raw)
            for _, raw in self._json_artifacts(
                "reviewed-sme-evidence", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        approved_clusters = [
            raw
            for _, raw in self._json_artifacts(
                "reviewed-learner-confusion-cluster", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        principles = [
            *distill_sme_evidence(approved_sme),
            *distill_learner_clusters(approved_clusters),
        ]
        existing_ids = {
            raw.get("principle_id")
            for _, raw in self._json_artifacts("principle-candidate")
        }
        outputs = []
        for principle in principles:
            if principle.principle_id in existing_ids:
                continue
            manifest = self.store.put_json(
                stage="principle_candidates",
                name=f"{principle.principle_id}.json",
                value=principle.to_dict(),
                artifact_type="principle-candidate",
                created_by="assessment-evolution-principle-distiller:v1",
                source_record_ids=[
                    *principle.positive_example_ids,
                    *principle.negative_example_ids,
                    *principle.learner_cluster_ids,
                ],
                validator_refs=[principle.schema_version],
                sensitivity="sanitized",
            )
            outputs.append(manifest.artifact_id)
        return outputs

    def review_principle(
        self,
        *,
        principle_id: str,
        decision: str,
        reviewer_id: str,
        reviewer_role: str,
    ) -> str:
        manifest, raw = self._find_json_by_id("principle-candidate", "principle_id", principle_id)
        if decision not in {"approved", "approved_with_edits", "rejected", "deferred"}:
            raise SchemaError("invalid principle review decision")
        if decision in {"approved", "approved_with_edits"} and reviewer_role != "sme":
            raise SchemaError("principle approval requires reviewer_role=sme")
        principle = AssessmentImprovementPrinciple.from_dict(raw)
        principle.review_status = decision
        principle = finalize_principle(principle)
        review_id = stable_id(
            "review",
            {
                "principle_id": principle_id,
                "reviewer_id": reviewer_id,
                "decision": decision,
                "time": utc_now(),
            },
        )
        output = self.store.put_json(
            stage="principle_bank",
            name=f"{principle_id}.{review_id}.json",
            value=principle.to_dict(),
            artifact_type="reviewed-principle",
            created_by="assessment-evolution-principle-review:v1",
            parent_artifact_ids=[manifest.artifact_id],
            source_record_ids=[
                principle_id,
                *principle.positive_example_ids,
                *principle.negative_example_ids,
                *principle.learner_cluster_ids,
            ],
            sensitivity="sanitized",
            metadata={
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role,
                "decision": decision,
            },
        )
        return output.artifact_id

    def curate_bank(
        self,
        *,
        evidence_bundle_id: str,
        measured_utility: float = 0.0,
        risk_penalty: float = 0.0,
    ) -> str:
        principles = [
            AssessmentImprovementPrinciple.from_dict(raw)
            for _, raw in self._json_artifacts(
                "reviewed-principle", newest_by_source=True
            )
            if raw.get("review_status") in {"approved", "approved_with_edits"}
        ]
        if not principles:
            raise SchemaError("no approved principles are available for curation")
        expected = {
            evidence_id
            for principle in principles
            for evidence_id in [
                *principle.positive_example_ids,
                *principle.negative_example_ids,
                *principle.learner_cluster_ids,
            ]
        }
        objectives = bank_metrics(
            principles,
            expected_evidence_ids=expected,
            measured_utility=measured_utility,
            risk_penalty=risk_penalty,
        )
        bank = create_bank(
            principles=principles,
            evidence_bundle_id=evidence_bundle_id,
            proposal_id=stable_id("proposal", sorted(expected)),
            objectives=objectives,
            operations=[
                {
                    "operation": "ADD",
                    "principle_id": principle.principle_id,
                    "reason": "Initial approved principle bank.",
                }
                for principle in principles
            ],
            hard_gates_passed=True,
        )
        bank = select_bank([bank])
        try:
            existing, _ = self._find_json_by_id(
                "selected-principle-bank", "bank_id", bank.bank_id
            )
            return existing.artifact_id
        except FileNotFoundError:
            pass
        manifest = self.store.put_json(
            stage="principle_bank",
            name=f"{bank.bank_id}.json",
            value=bank.to_dict(),
            artifact_type="selected-principle-bank",
            created_by="assessment-evolution-bank-curator:v1",
            source_record_ids=sorted(expected),
            validator_refs=[bank.schema_version],
            sensitivity="sanitized",
        )
        return manifest.artifact_id

    def compile_skill(self, *, bank_id: str, token_budget: int = 8000) -> str:
        bank_manifest, raw = self._find_json_by_id(
            "selected-principle-bank", "bank_id", bank_id
        )
        bank = PrincipleBankVersion.from_dict(raw)
        compilation = compile_improvement_skill(bank, token_budget=token_budget)
        skill_manifest = self.store.put_text(
            stage="compiled_skill",
            name="best_skill.md",
            text=compilation.skill_markdown,
            artifact_type="compiled-improvement-skill",
            created_by="assessment-evolution-compiler:v1",
            parent_artifact_ids=[bank_manifest.artifact_id],
            source_record_ids=bank.principle_versions,
            validator_refs=["improvement-skill-compiler:v1"],
            sensitivity="sanitized",
            metadata={"bank_id": bank.bank_id},
        )
        self.store.put_json(
            stage="compiled_skill",
            name="compilation-manifest.json",
            value=compilation.manifest,
            artifact_type="improvement-skill-compilation",
            created_by="assessment-evolution-compiler:v1",
            parent_artifact_ids=[bank_manifest.artifact_id, skill_manifest.artifact_id],
            source_record_ids=bank.principle_versions,
            sensitivity="sanitized",
        )
        return skill_manifest.artifact_id

    def evolve_target(
        self,
        *,
        target_envelope_path: Path,
        domain_profile_path: Path,
        evidence_path: Path,
        improvement_skill_path: Path | None = None,
    ) -> str:
        envelope = TargetSkillEnvelope.from_dict(
            json.loads(target_envelope_path.read_text(encoding="utf-8"))
        )
        domain = DomainProfile.from_dict(
            json.loads(domain_profile_path.read_text(encoding="utf-8"))
        )
        if not domain.approved:
            raise SchemaError("domain profile must be approved before target evolution")
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence_items = evidence_payload.get("items") or []
        approved_ids = {
            str(item.get("evidence_id") or item.get("cluster_id"))
            for item in evidence_items
            if item.get("review_status") in {"approved", "approved_with_edits"}
        }
        skill = (
            improvement_skill_path.read_text(encoding="utf-8")
            if improvement_skill_path
            else self._latest_text("compiled-improvement-skill")
        )
        governing = load_prompt("target-skill-evolver")
        combined = Prompt(
            name="compiled-improvement-skill+target-skill-evolver",
            text=skill + "\n\n" + governing.text,
            git_hash=content_hash(
                {"skill_hash": content_hash(skill), "prompt_hash": governing.git_hash}
            ),
            path=governing.path,
        )
        client = StructuredModelClient(
            ModelSettings.from_env(), observability=self.observability
        )
        raw, model_ref = client.generate_json(
            prompt=combined,
            user_payload={
                "target_skill_envelope": envelope.to_dict(),
                "domain_profile": domain.to_dict(),
                "approved_evidence": evidence_items,
            },
            observation_name="skillopt.evolve-target",
        )
        result, gates = evolution_from_model(
            raw, envelope=envelope, approved_evidence_ids=approved_ids
        )
        manifest = self.store.put_json(
            stage="skillopt",
            name=f"{stable_id('evolution', result.to_dict())}.json",
            value=result.to_dict(),
            artifact_type="target-skill-evolution",
            created_by="assessment-evolution-target-evolver:v1",
            source_record_ids=[envelope.target_skill_id, *sorted(approved_ids)],
            prompt_refs=[
                {"name": combined.name, "git_hash": combined.git_hash}
            ],
            model_refs=[model_ref],
            validator_refs=[result.schema_version, "evolution-hard-gates:v1"],
            sensitivity="sanitized",
            metadata={
                "decision": result.decision,
                "target_skill_id": envelope.target_skill_id,
                "hard_gates_passed": all(
                    value
                    for key, value in gates.items()
                    if not key.endswith("_detected")
                )
                and not any(
                    value for key, value in gates.items() if key.endswith("_detected")
                ),
            },
        )
        self.observability.flush()
        return manifest.artifact_id

    def prepare_release(
        self,
        *,
        evolution_result_id: str,
        target_skill_id: str,
        prior_version: str,
        proposed_version: str,
        evaluation_ids: list[str],
        rollback: dict[str, Any],
    ) -> str:
        proposal = ReleaseProposal(
            release_id=stable_id(
                "release",
                {
                    "evolution_result_id": evolution_result_id,
                    "target_skill_id": target_skill_id,
                    "proposed_version": proposed_version,
                },
            ),
            evolution_result_id=evolution_result_id,
            target_skill_id=target_skill_id,
            prior_version=prior_version,
            proposed_version=proposed_version,
            artifact_ids=[evolution_result_id],
            evaluation_ids=evaluation_ids,
            status="proposed",
            rollback=rollback,
        )
        proposal.validate()
        manifest = self.store.put_json(
            stage="release",
            name=f"{proposal.release_id}.json",
            value=proposal.to_dict(),
            artifact_type="release-proposal",
            created_by="assessment-evolution-release:v1",
            source_record_ids=[evolution_result_id, *evaluation_ids],
            validator_refs=[proposal.schema_version],
            sensitivity="sanitized",
            metadata={"status": "proposed", "promotion_performed": False},
        )
        return manifest.artifact_id

    def review_release(
        self,
        *,
        release_id: str,
        decision: str,
        reviewer_id: str,
        reviewer_role: str,
        comment: str | None = None,
    ) -> str:
        manifest, raw = self._find_json_by_id("release-proposal", "release_id", release_id)
        if decision not in {"approved", "rejected"}:
            raise SchemaError("release decision must be approved or rejected")
        proposal = ReleaseProposal.from_dict(raw)
        approval = {
            "approval_id": stable_id(
                "approval",
                {
                    "release_id": release_id,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "time": utc_now(),
                },
            ),
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "decision": decision,
            "comment": comment,
            "reviewed_at": utc_now(),
        }
        proposal.approvals.append(approval)
        proposal.status = decision
        proposal.validate()
        output = self.store.put_json(
            stage="release",
            name=f"{release_id}.{approval['approval_id']}.json",
            value=proposal.to_dict(),
            artifact_type="reviewed-release-proposal",
            created_by="assessment-evolution-release-review:v1",
            parent_artifact_ids=[manifest.artifact_id],
            source_record_ids=[release_id],
            validator_refs=[proposal.schema_version],
            sensitivity="sanitized",
            metadata={
                "status": decision,
                "reviewer_role": reviewer_role,
                "promotion_performed": False,
            },
        )
        return output.artifact_id

    def _json_artifacts(
        self,
        artifact_type: str,
        *,
        newest_by_source: bool = False,
    ) -> list[tuple[Any, dict[str, Any]]]:
        rows = []
        for manifest in self.store.artifacts():
            if manifest.artifact_type != artifact_type:
                continue
            path = self.store.run_dir / manifest.relative_path
            rows.append((manifest, json.loads(path.read_text(encoding="utf-8"))))
        if not newest_by_source:
            return rows
        latest: dict[str, tuple[Any, dict[str, Any]]] = {}
        for manifest, raw in rows:
            key = str(
                raw.get("evidence_id")
                or raw.get("cluster_id")
                or raw.get("principle_id")
                or manifest.artifact_id
            )
            latest[key] = (manifest, raw)
        return list(latest.values())

    def _find_evidence(self, evidence_id: str) -> tuple[Any, dict[str, Any]]:
        for artifact_type in ("sme-evidence-candidate", "learner-evidence-candidate"):
            for manifest, raw in self._json_artifacts(artifact_type):
                if raw.get("evidence_id") == evidence_id:
                    return manifest, raw
        raise FileNotFoundError(f"evidence candidate {evidence_id} not found")

    def _find_json_by_id(
        self, artifact_type: str, field: str, value: str
    ) -> tuple[Any, dict[str, Any]]:
        for manifest, raw in reversed(self._json_artifacts(artifact_type)):
            if raw.get(field) == value:
                return manifest, raw
        raise FileNotFoundError(f"{artifact_type} {value} not found")

    def _latest_text(self, artifact_type: str) -> str:
        for manifest in reversed(self.store.artifacts()):
            if manifest.artifact_type == artifact_type:
                return (self.store.run_dir / manifest.relative_path).read_text(encoding="utf-8")
        raise FileNotFoundError(f"no {artifact_type} artifact in run")
