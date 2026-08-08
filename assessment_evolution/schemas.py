"""Versioned data contracts for the assessment-evolution pipeline."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar, TypeVar


class SchemaError(ValueError):
    """Raised when an artifact violates a public pipeline contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    raw = value if isinstance(value, str) else canonical_json(value)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{content_hash(value).removeprefix('sha256:')[:24]}"


def _required(value: Any, name: str) -> None:
    if value is None or value == "" or value == []:
        raise SchemaError(f"{name} is required")


def _enum(value: str, allowed: set[str], name: str) -> None:
    if value not in allowed:
        raise SchemaError(f"{name} must be one of {sorted(allowed)}; got {value!r}")


def _ratio(value: float, name: str) -> None:
    if not 0 <= float(value) <= 1:
        raise SchemaError(f"{name} must be between 0 and 1")


def _timestamp(value: str | None, name: str, *, required: bool = True) -> datetime | None:
    if value is None:
        if required:
            raise SchemaError(f"{name} is required")
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaError(f"{name} must be an ISO-8601 timestamp") from exc


T = TypeVar("T", bound="VersionedRecord")


@dataclass(slots=True)
class VersionedRecord:
    """Base for strict, JSON-serializable versioned contracts."""

    SCHEMA: ClassVar[str] = ""
    schema_version: str = ""

    def validate(self) -> None:
        if self.schema_version != self.SCHEMA:
            raise SchemaError(
                f"unsupported schema_version {self.schema_version!r}; expected {self.SCHEMA!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        if not isinstance(data, dict):
            raise SchemaError(f"{cls.__name__} must be a JSON object")
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise SchemaError(f"{cls.__name__} has unknown fields: {sorted(unknown)}")
        record = cls(**copy.deepcopy(data))
        record.validate()
        return record


@dataclass(slots=True)
class SourceSpan(VersionedRecord):
    SCHEMA: ClassVar[str] = "source-span/1"
    schema_version: str = SCHEMA
    span_id: str = ""
    conversation_id: str = ""
    message_id: str = ""
    start_char: int = 0
    end_char: int = 0
    text_hash: str = ""
    sanitized_excerpt: str = ""
    redaction_labels: list[str] = field(default_factory=list)

    def validate(self) -> None:
        super(SourceSpan, self).validate()
        for name in ("span_id", "conversation_id", "message_id", "text_hash"):
            _required(getattr(self, name), name)
        if self.start_char < 0 or self.end_char <= self.start_char:
            raise SchemaError("source span offsets must be non-negative and non-empty")
        if not self.text_hash.startswith("sha256:"):
            raise SchemaError("text_hash must use sha256:<hex>")


@dataclass(slots=True)
class ConversationRecord(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-conversation/1"
    schema_version: str = SCHEMA
    conversation_id: str = ""
    source: str = ""
    source_conversation_id: str = ""
    source_uri: str | None = None
    source_hash: str = ""
    persona: str = "unknown"
    participant_ids: list[str] = field(default_factory=list)
    assessment_id: str | None = None
    assessment_version: str | None = None
    target_skill_id: str | None = None
    domain: str | None = None
    cohort_id: str | None = None
    started_at: str = ""
    ended_at: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    consent: dict[str, bool] = field(default_factory=dict)
    retention_class: str = ""
    ingested_at: str = field(default_factory=utc_now)
    normalizer_version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        super(ConversationRecord, self).validate()
        for name in (
            "conversation_id",
            "source",
            "source_conversation_id",
            "source_hash",
            "started_at",
            "retention_class",
        ):
            _required(getattr(self, name), name)
        _enum(self.persona, {"sme", "learner", "mixed", "unknown"}, "persona")
        start = _timestamp(self.started_at, "started_at")
        end = _timestamp(self.ended_at, "ended_at", required=False)
        _timestamp(self.ingested_at, "ingested_at")
        if start and end and end < start:
            raise SchemaError("ended_at cannot precede started_at")
        if not self.source_hash.startswith("sha256:"):
            raise SchemaError("source_hash must use sha256:<hex>")
        if not isinstance(self.consent, dict) or not {
            "assessment_improvement",
            "llm_processing",
            "telemetry_redacted",
        }.issubset(self.consent):
            raise SchemaError("consent must contain all processing decisions")
        if not self.messages:
            raise SchemaError("messages must not be empty")
        sequences: list[int] = []
        message_ids: set[str] = set()
        for message in self.messages:
            required = {
                "message_id",
                "sequence",
                "role",
                "speaker_persona",
                "timestamp",
                "content",
                "content_hash",
                "source_message_id",
                "attachment_ids",
                "redaction_state",
            }
            if set(message) != required:
                raise SchemaError(
                    f"message fields must be exactly {sorted(required)}"
                )
            _enum(message["role"], {"system", "user", "assistant", "tool"}, "message.role")
            _enum(message["redaction_state"], {"raw", "sanitized", "quarantined"}, "redaction_state")
            if message["speaker_persona"] not in {None, "sme", "learner", "agent", "system"}:
                raise SchemaError("invalid speaker_persona")
            if content_hash(message["content"]) != message["content_hash"]:
                raise SchemaError(f"content_hash mismatch for {message['message_id']}")
            sequences.append(int(message["sequence"]))
            if message["message_id"] in message_ids:
                raise SchemaError("message_id values must be unique")
            message_ids.add(message["message_id"])
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise SchemaError("message sequence values must be strictly increasing")


SME_CATEGORIES = {
    "assessment_brief",
    "learning_objective",
    "competency_coverage",
    "question_design_rule",
    "scenario_design_rule",
    "difficulty_rule",
    "distractor_rule",
    "scoring_rule",
    "answer_key_rule",
    "feedback_rule",
    "format_contract",
    "tool_workflow",
    "quality_constraint",
    "correction_pair",
    "accepted_choice",
    "rejected_choice",
    "exception",
    "positive_example",
    "negative_example",
}
REVIEW_STATES = {
    "pending",
    "approved",
    "approved_with_edits",
    "rejected",
    "duplicate",
    "deferred",
    "superseded",
}
LEARNER_CATEGORIES = {
    "instruction_ambiguity",
    "undefined_terminology",
    "expected_output_unclear",
    "assessment_scope_unclear",
    "environment_or_tool_confusion",
    "navigation_confusion",
    "prerequisite_not_communicated",
    "feedback_unclear",
    "conflicting_requirements",
    "example_or_format_mismatch",
}


@dataclass(slots=True)
class SMEEvidence(VersionedRecord):
    SCHEMA: ClassVar[str] = "sme-evidence/1"
    schema_version: str = SCHEMA
    evidence_id: str = ""
    category: str = ""
    claim: str = ""
    rationale: str | None = None
    failure_mechanism: str | None = None
    recommended_behavior: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    positive_example: str | None = None
    negative_example: str | None = None
    applicability: dict[str, Any] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)
    source_spans: list[dict[str, Any]] = field(default_factory=list)
    extractor_confidence: float = 0.0
    inference_level: str = "weak_inference"
    review_status: str = "pending"
    supersedes: list[str] = field(default_factory=list)
    created_by: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        super(SMEEvidence, self).validate()
        for name in ("evidence_id", "claim"):
            _required(getattr(self, name), name)
        _enum(self.category, SME_CATEGORIES, "category")
        _enum(self.inference_level, {"explicit", "strong_inference", "weak_inference"}, "inference_level")
        _enum(self.review_status, REVIEW_STATES, "review_status")
        _ratio(self.extractor_confidence, "extractor_confidence")
        if not self.source_spans:
            raise SchemaError("SME evidence must have at least one source span")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class LearnerConfusionEvidence(VersionedRecord):
    SCHEMA: ClassVar[str] = "learner-confusion/1"
    schema_version: str = SCHEMA
    evidence_id: str = ""
    category: str = ""
    assessment_id: str | None = None
    assessment_version: str | None = None
    assessment_element_id: str | None = None
    confusion_statement: str = ""
    observable_signal: str = ""
    likely_cause: str | None = None
    proposed_clarity_need: str | None = None
    severity: str = "low"
    solution_content_detected: bool = False
    source_spans: list[dict[str, Any]] = field(default_factory=list)
    learner_pseudonym: str = ""
    cluster_id: str | None = None
    extractor_confidence: float = 0.0
    review_status: str = "pending"
    created_by: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        super(LearnerConfusionEvidence, self).validate()
        for name in ("evidence_id", "confusion_statement", "observable_signal", "learner_pseudonym"):
            _required(getattr(self, name), name)
        _enum(self.category, LEARNER_CATEGORIES, "category")
        _enum(self.severity, {"low", "medium", "high", "blocking"}, "severity")
        _enum(self.review_status, REVIEW_STATES, "review_status")
        _ratio(self.extractor_confidence, "extractor_confidence")
        if not self.source_spans:
            raise SchemaError("learner evidence must have at least one source span")
        if self.review_status in {"approved", "approved_with_edits"} and self.solution_content_detected:
            raise SchemaError("solution-bearing learner evidence cannot be approved")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class EvidenceReview(VersionedRecord):
    SCHEMA: ClassVar[str] = "evidence-review/1"
    schema_version: str = SCHEMA
    review_id: str = ""
    evidence_id: str = ""
    decision: str = ""
    reviewer_id: str = ""
    reviewer_role: str = ""
    reason_codes: list[str] = field(default_factory=list)
    comment: str | None = None
    field_corrections: dict[str, Any] = field(default_factory=dict)
    reviewed_at: str = field(default_factory=utc_now)
    policy_version: str = "evidence-review-policy/1"
    langfuse_trace_id: str | None = None

    def validate(self) -> None:
        super(EvidenceReview, self).validate()
        for name in ("review_id", "evidence_id", "reviewer_id", "reviewer_role", "policy_version"):
            _required(getattr(self, name), name)
        _enum(self.decision, REVIEW_STATES - {"pending"}, "decision")
        if not self.reason_codes:
            raise SchemaError("reason_codes must not be empty")
        _timestamp(self.reviewed_at, "reviewed_at")


@dataclass(slots=True)
class EvidenceBundle(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-evidence-bundle/1"
    schema_version: str = SCHEMA
    bundle_id: str = ""
    created_at: str = field(default_factory=utc_now)
    cutoff_at: str = field(default_factory=utc_now)
    domain_profile_id: str = ""
    target_scope: list[str] = field(default_factory=list)
    sme_evidence_ids: list[str] = field(default_factory=list)
    learner_cluster_ids: list[str] = field(default_factory=list)
    excluded_evidence: list[dict[str, str]] = field(default_factory=list)
    split_manifest: str = ""
    review_manifest: str = ""
    statistics: dict[str, int] = field(default_factory=dict)
    content_hash: str = ""

    def validate(self) -> None:
        super(EvidenceBundle, self).validate()
        for name in ("bundle_id", "domain_profile_id", "split_manifest", "review_manifest"):
            _required(getattr(self, name), name)
        _timestamp(self.created_at, "created_at")
        _timestamp(self.cutoff_at, "cutoff_at")
        if self.content_hash and not self.content_hash.startswith("sha256:"):
            raise SchemaError("content_hash must use sha256:<hex>")
        if self.content_hash:
            raw = asdict(self)
            raw["content_hash"] = ""
            if content_hash(raw) != self.content_hash:
                raise SchemaError("evidence bundle content_hash mismatch")


@dataclass(slots=True)
class AssessmentImprovementPrinciple(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-principle/1"
    schema_version: str = SCHEMA
    principle_id: str = ""
    version: int = 1
    parent_version_id: str | None = None
    title: str = ""
    principle: str = ""
    when_to_apply: list[str] = field(default_factory=list)
    when_not_to_apply: list[str] = field(default_factory=list)
    failure_mechanism: str = ""
    remedy: list[str] = field(default_factory=list)
    high_risk_blacklist: list[str] = field(default_factory=list)
    validation_expectations: list[str] = field(default_factory=list)
    positive_example_ids: list[str] = field(default_factory=list)
    negative_example_ids: list[str] = field(default_factory=list)
    learner_cluster_ids: list[str] = field(default_factory=list)
    assessment_types: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    target_capabilities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    review_status: str = "pending"
    utility_history: list[dict[str, Any]] = field(default_factory=list)
    coverage_clusters: list[str] = field(default_factory=list)
    redundancy_links: list[dict[str, Any]] = field(default_factory=list)
    contradiction_links: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    content_hash: str = ""

    def validate(self) -> None:
        super(AssessmentImprovementPrinciple, self).validate()
        for name in ("principle_id", "title", "principle", "failure_mechanism"):
            _required(getattr(self, name), name)
        if self.version < 1:
            raise SchemaError("principle version must be positive")
        if not self.remedy or not self.validation_expectations:
            raise SchemaError("principle requires remedy and validation expectations")
        if not self.positive_example_ids and not self.negative_example_ids and not self.learner_cluster_ids:
            raise SchemaError("principle must cite evidence")
        _ratio(self.confidence, "confidence")
        _enum(self.review_status, REVIEW_STATES, "review_status")
        if self.content_hash and not self.content_hash.startswith("sha256:"):
            raise SchemaError("content_hash must use sha256:<hex>")
        if self.content_hash:
            raw = asdict(self)
            raw["content_hash"] = ""
            if content_hash(raw) != self.content_hash:
                raise SchemaError("principle content_hash mismatch")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class PrincipleBankVersion(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-principle-bank/1"
    schema_version: str = SCHEMA
    bank_id: str = ""
    version: int = 1
    parent_bank_version: str | None = None
    principle_versions: list[str] = field(default_factory=list)
    evidence_bundle_id: str = ""
    proposal_id: str = ""
    objectives: dict[str, float | int] = field(default_factory=dict)
    hard_gates_passed: bool = False
    pareto_status: str = "candidate"
    created_at: str = field(default_factory=utc_now)
    content_hash: str = ""
    principles: list[dict[str, Any]] = field(default_factory=list)
    proposal_operations: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        super(PrincipleBankVersion, self).validate()
        _required(self.bank_id, "bank_id")
        _required(self.evidence_bundle_id, "evidence_bundle_id")
        _required(self.proposal_id, "proposal_id")
        if self.version < 1:
            raise SchemaError("bank version must be positive")
        _enum(self.pareto_status, {"candidate", "frontier", "selected", "rejected"}, "pareto_status")
        ids: set[str] = set()
        for raw in self.principles:
            principle = AssessmentImprovementPrinciple.from_dict(raw)
            if principle.principle_id in ids:
                raise SchemaError("principle IDs must be unique in a bank")
            ids.add(principle.principle_id)
            identity = f"{principle.principle_id}:v{principle.version}"
            if identity not in self.principle_versions:
                raise SchemaError(f"principle_versions is missing {identity}")
        for name in ("utility", "diversity", "coverage", "risk_penalty"):
            if name in self.objectives:
                _ratio(float(self.objectives[name]), f"objectives.{name}")
        if self.content_hash and not self.content_hash.startswith("sha256:"):
            raise SchemaError("content_hash must use sha256:<hex>")
        if self.content_hash:
            raw = asdict(self)
            raw["content_hash"] = ""
            if content_hash(raw) != self.content_hash:
                raise SchemaError("principle bank content_hash mismatch")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class TargetSkillEnvelope(VersionedRecord):
    SCHEMA: ClassVar[str] = "target-assessment-skill-envelope/1"
    schema_version: str = SCHEMA
    target_skill_id: str = ""
    display_name: str = ""
    input_version: str = ""
    input_content_hash: str = ""
    exact_skill_markdown: str = ""
    domain_profile_id: str = ""
    owner: str = ""
    status: str = "draft"
    required_frontmatter: dict[str, dict[str, Any]] = field(default_factory=dict)
    immutable_sections: dict[str, str] = field(default_factory=dict)
    required_sections: list[str] = field(default_factory=list)
    input_contract: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    tool_contracts: list[dict[str, Any]] = field(default_factory=list)
    script_contracts: list[dict[str, Any]] = field(default_factory=list)
    reference_contracts: list[dict[str, Any]] = field(default_factory=list)
    protected_behaviors: list[dict[str, Any]] = field(default_factory=list)
    permitted_change_areas: list[str] = field(default_factory=list)
    validators: list[dict[str, Any]] = field(default_factory=list)
    rollback: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        super(TargetSkillEnvelope, self).validate()
        for name in (
            "target_skill_id",
            "display_name",
            "input_version",
            "input_content_hash",
            "exact_skill_markdown",
            "domain_profile_id",
            "owner",
        ):
            _required(getattr(self, name), name)
        if content_hash(self.exact_skill_markdown) != self.input_content_hash:
            raise SchemaError("input_content_hash does not match exact_skill_markdown")
        _enum(self.status, {"draft", "staging", "production", "retired"}, "status")
        for index, contract in enumerate(self.tool_contracts):
            if contract.get("required", True) and not (
                contract.get("tool_id") or contract.get("id") or contract.get("tool")
            ):
                raise SchemaError(f"required tool contract {index} lacks an identifier")
        for index, contract in enumerate(self.script_contracts):
            if contract.get("required", True) and not (
                contract.get("script") or contract.get("id")
            ):
                raise SchemaError(f"required script contract {index} lacks an identifier")


@dataclass(slots=True)
class DomainProfile(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-domain-profile/1"
    schema_version: str = SCHEMA
    profile_id: str = ""
    version: str = ""
    domain: str = ""
    authoritative_terminology: dict[str, str] = field(default_factory=dict)
    competency_taxonomy: list[dict[str, Any]] = field(default_factory=list)
    assessment_types: list[str] = field(default_factory=list)
    difficulty_model: dict[str, Any] = field(default_factory=dict)
    protected_policies: list[str] = field(default_factory=list)
    approved_references: list[dict[str, Any]] = field(default_factory=list)
    validators: list[dict[str, Any]] = field(default_factory=list)
    prohibited_behavior: list[str] = field(default_factory=list)
    owner: str = ""
    approved: bool = False

    def validate(self) -> None:
        super(DomainProfile, self).validate()
        for name in ("profile_id", "version", "domain", "owner"):
            _required(getattr(self, name), name)


@dataclass(slots=True)
class BenchmarkItem(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-improver-benchmark/1"
    schema_version: str = SCHEMA
    id: str = ""
    split: str = "train"
    split_group: str = ""
    target_skill_envelope: dict[str, Any] = field(default_factory=dict)
    domain_profile: dict[str, Any] = field(default_factory=dict)
    assessment_brief: dict[str, Any] = field(default_factory=dict)
    evidence_bundle: dict[str, Any] = field(default_factory=dict)
    expected_behaviors: list[dict[str, Any]] = field(default_factory=list)
    protected_behaviors: list[dict[str, Any]] = field(default_factory=list)
    deterministic_validators: list[str] = field(default_factory=list)
    consumer_config: dict[str, Any] = field(default_factory=dict)
    expected_output: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        super(BenchmarkItem, self).validate()
        _required(self.id, "id")
        _required(self.split_group, "split_group")
        _enum(self.split, {"train", "validation", "test", "observation"}, "split")
        TargetSkillEnvelope.from_dict(self.target_skill_envelope)
        DomainProfile.from_dict(self.domain_profile)
        bundle_manifest = self.evidence_bundle.get("manifest", self.evidence_bundle)
        EvidenceBundle.from_dict(bundle_manifest)


@dataclass(slots=True)
class EvolutionResult(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-skill-evolution-result/1"
    schema_version: str = SCHEMA
    decision: str = "needs_review"
    summary: str = ""
    target_skill: dict[str, Any] = field(default_factory=dict)
    evolved_skill_markdown: str = ""
    patch: list[dict[str, Any]] = field(default_factory=list)
    evidence_coverage: list[dict[str, Any]] = field(default_factory=list)
    preserved_contracts: list[dict[str, Any]] = field(default_factory=list)
    learner_clarity_actions: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, bool] = field(default_factory=dict)
    risks: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    recommended_review_focus: list[str] = field(default_factory=list)

    def validate(self) -> None:
        super(EvolutionResult, self).validate()
        _required(self.summary, "summary")
        _enum(self.decision, {"update", "no_change", "needs_review"}, "decision")
        required_target = {
            "skill_id",
            "input_version",
            "input_hash",
            "output_version_proposal",
            "output_hash",
        }
        if set(self.target_skill) != required_target:
            raise SchemaError(f"target_skill fields must be exactly {sorted(required_target)}")
        if content_hash(self.evolved_skill_markdown) != self.target_skill["output_hash"]:
            raise SchemaError("evolved_skill_hash does not match evolved skill")
        if self.decision == "update" and not self.patch:
            raise SchemaError("update requires at least one patch operation")
        if self.decision in {"no_change", "needs_review"} and self.patch:
            raise SchemaError(f"{self.decision} must not contain patch operations")


@dataclass(slots=True)
class EvaluationResult(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-evolution-evaluation/1"
    schema_version: str = SCHEMA
    evaluation_id: str = ""
    benchmark_item_id: str = ""
    candidate_id: str = ""
    split: str = ""
    hard_gates: dict[str, bool] = field(default_factory=dict)
    soft_scores: dict[str, float] = field(default_factory=dict)
    weighted_score: float = 0.0
    baseline_score: float | None = None
    performance_delta: float | None = None
    negative_transfer: bool = False
    evaluator_refs: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        super(EvaluationResult, self).validate()
        for name in ("evaluation_id", "benchmark_item_id", "candidate_id"):
            _required(getattr(self, name), name)
        _enum(self.split, {"train", "validation", "test"}, "split")
        for name, score in self.soft_scores.items():
            _ratio(float(score), f"soft_scores.{name}")
        _ratio(self.weighted_score, "weighted_score")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class ArtifactManifest(VersionedRecord):
    SCHEMA: ClassVar[str] = "artifact-manifest/1"
    schema_version: str = SCHEMA
    artifact_id: str = ""
    artifact_version: int = 1
    artifact_type: str = ""
    relative_path: str = ""
    media_type: str = ""
    content_hash: str = ""
    byte_size: int = 0
    payload_schema_version: str | None = None
    parent_artifact_ids: list[str] = field(default_factory=list)
    source_record_ids: list[str] = field(default_factory=list)
    prompt_refs: list[dict[str, Any]] = field(default_factory=list)
    model_refs: list[dict[str, Any]] = field(default_factory=list)
    validator_refs: list[str] = field(default_factory=list)
    langfuse_trace_ids: list[str] = field(default_factory=list)
    status: str = "complete"
    created_at: str = field(default_factory=utc_now)
    created_by: str = ""
    sensitivity: str = "sanitized"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        super(ArtifactManifest, self).validate()
        for name in (
            "artifact_id",
            "artifact_type",
            "relative_path",
            "media_type",
            "content_hash",
            "created_by",
        ):
            _required(getattr(self, name), name)
        if self.artifact_version < 1 or self.byte_size < 0:
            raise SchemaError("artifact version and byte size must be non-negative")
        _enum(self.status, {"complete", "failed", "quarantined"}, "status")
        _enum(self.sensitivity, {"restricted", "sanitized", "public"}, "sensitivity")
        _timestamp(self.created_at, "created_at")


@dataclass(slots=True)
class ReleaseProposal(VersionedRecord):
    SCHEMA: ClassVar[str] = "assessment-release-proposal/1"
    schema_version: str = SCHEMA
    release_id: str = ""
    evolution_result_id: str = ""
    target_skill_id: str = ""
    prior_version: str = ""
    proposed_version: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    evaluation_ids: list[str] = field(default_factory=list)
    status: str = "proposed"
    required_approver_roles: list[str] = field(default_factory=lambda: ["sme"])
    approvals: list[dict[str, Any]] = field(default_factory=list)
    rollback: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        super(ReleaseProposal, self).validate()
        for name in (
            "release_id",
            "evolution_result_id",
            "target_skill_id",
            "prior_version",
            "proposed_version",
        ):
            _required(getattr(self, name), name)
        _enum(
            self.status,
            {"proposed", "under_review", "approved", "rejected", "withdrawn", "promoted", "rolled_back"},
            "status",
        )
        if self.status in {"approved", "promoted"}:
            approved_roles = {
                approval.get("reviewer_role")
                for approval in self.approvals
                if approval.get("decision") == "approved"
            }
            if not set(self.required_approver_roles).issubset(approved_roles):
                raise SchemaError("release lacks all required role approvals")
        _timestamp(self.created_at, "created_at")
