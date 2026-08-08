"""Evidence extraction, human review, aggregation, and bundle admission."""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from .privacy import classify_learner_span, detect_learner_solution
from .schemas import (
    ConversationRecord,
    EvidenceBundle,
    EvidenceReview,
    LearnerConfusionEvidence,
    SMEEvidence,
    SchemaError,
    SourceSpan,
    content_hash,
    stable_id,
    utc_now,
)


def source_span(
    record: ConversationRecord,
    message: dict[str, Any],
    *,
    start: int = 0,
    end: int | None = None,
    excerpt_limit: int = 500,
    labels: list[str] | None = None,
) -> SourceSpan:
    text = message["content"]
    end = len(text) if end is None else end
    selected = text[start:end]
    span = SourceSpan(
        span_id=stable_id(
            "span",
            {
                "conversation_id": record.conversation_id,
                "message_id": message["message_id"],
                "start": start,
                "end": end,
                "hash": content_hash(selected),
            },
        ),
        conversation_id=record.conversation_id,
        message_id=message["message_id"],
        start_char=start,
        end_char=end,
        text_hash=content_hash(selected),
        sanitized_excerpt=selected[:excerpt_limit],
        redaction_labels=labels or [],
    )
    span.validate()
    return span


_SME_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("correction_pair", re.compile(r"(?i)\b(?:instead|change|revise|correct|not .* but)\b")),
    ("rejected_choice", re.compile(r"(?i)\b(?:reject|do not|don't|must not|avoid)\b")),
    ("accepted_choice", re.compile(r"(?i)\b(?:approved|accept|looks correct|this works)\b")),
    ("difficulty_rule", re.compile(r"(?i)\b(?:difficulty|advanced|intermediate|beginner|cognitive)\b")),
    ("scoring_rule", re.compile(r"(?i)\b(?:rubric|score|grading|evaluation criteria)\b")),
    ("format_contract", re.compile(r"(?i)\b(?:format|schema|field|required output)\b")),
    ("scenario_design_rule", re.compile(r"(?i)\b(?:scenario|realistic context)\b")),
    ("quality_constraint", re.compile(r"(?i)\b(?:must|require|ensure|quality)\b")),
]


def extract_sme_candidates(record: ConversationRecord) -> list[SMEEvidence]:
    """Offline explicit-signal fallback; model extraction can add richer candidates."""
    record.validate()
    if record.persona != "sme":
        raise SchemaError("authoritative SME extraction requires persona=sme")
    if not record.consent.get("assessment_improvement"):
        raise SchemaError("conversation lacks assessment_improvement consent")
    out: list[SMEEvidence] = []
    for message in record.messages:
        if message["speaker_persona"] != "sme":
            continue
        category = next(
            (candidate for candidate, pattern in _SME_SIGNALS if pattern.search(message["content"])),
            None,
        )
        if not category:
            continue
        span = source_span(record, message)
        claim = " ".join(message["content"].split())
        evidence = SMEEvidence(
            evidence_id=stable_id(
                "sme_ev",
                {"span_id": span.span_id, "category": category, "claim": claim},
            ),
            category=category,
            claim=claim,
            applicability={
                "domains": [record.domain] if record.domain else [],
                "assessment_ids": [record.assessment_id] if record.assessment_id else [],
            },
            source_spans=[span.to_dict()],
            extractor_confidence=0.55,
            inference_level="explicit",
            created_by={
                "component": "deterministic-explicit-signal-extractor",
                "version": "1",
                "requires_model_enrichment": True,
            },
        )
        evidence.validate()
        out.append(evidence)
    return out


def sme_candidates_from_model(
    record: ConversationRecord, items: Iterable[dict[str, Any]], *, model_ref: dict[str, Any]
) -> list[SMEEvidence]:
    """Validate structured model output and bind every item to real source text."""
    by_id = {message["message_id"]: message for message in record.messages}
    out: list[SMEEvidence] = []
    for index, supplied in enumerate(items):
        raw = copy.deepcopy(supplied)
        message_id = str(raw.pop("message_id", ""))
        start = int(raw.pop("start_char", 0))
        end = int(raw.pop("end_char", 0))
        message = by_id.get(message_id)
        if message is None or start < 0 or end <= start or end > len(message["content"]):
            raise SchemaError(f"model evidence item {index} has invalid source offsets")
        span = source_span(record, message, start=start, end=end)
        raw["schema_version"] = SMEEvidence.SCHEMA
        raw.setdefault(
            "evidence_id",
            stable_id("sme_ev", {"span": span.span_id, "claim": raw.get("claim")}),
        )
        raw["source_spans"] = [span.to_dict()]
        raw.setdefault("created_by", model_ref)
        raw.setdefault("created_at", utc_now())
        evidence = SMEEvidence.from_dict(raw)
        out.append(evidence)
    return out


def extract_learner_candidates(record: ConversationRecord) -> list[LearnerConfusionEvidence]:
    record.validate()
    if record.persona != "learner":
        raise SchemaError("learner extraction requires persona=learner")
    if not record.consent.get("assessment_improvement"):
        raise SchemaError("conversation lacks assessment_improvement consent")
    learner_id = record.participant_ids[0] if record.participant_ids else stable_id(
        "learner", record.conversation_id
    )
    out = []
    for message in record.messages:
        if message["speaker_persona"] != "learner":
            continue
        boundary, category, labels = classify_learner_span(message["content"])
        if boundary != "assessment_understanding" or not category:
            continue
        if detect_learner_solution(message["content"]):
            continue
        span = source_span(record, message, labels=labels)
        normalized = " ".join(message["content"].split())
        evidence = LearnerConfusionEvidence(
            evidence_id=stable_id(
                "learner_ev",
                {"span_id": span.span_id, "category": category},
            ),
            category=category,
            assessment_id=record.assessment_id,
            assessment_version=record.assessment_version,
            confusion_statement=normalized,
            observable_signal=normalized,
            severity="medium",
            source_spans=[span.to_dict()],
            learner_pseudonym=learner_id,
            extractor_confidence=0.7,
            created_by={
                "component": "deterministic-learner-boundary-classifier",
                "version": "1",
            },
        )
        evidence.validate()
        out.append(evidence)
    return out


def review_evidence(
    evidence: SMEEvidence | LearnerConfusionEvidence,
    review: EvidenceReview,
) -> SMEEvidence | LearnerConfusionEvidence:
    evidence.validate()
    review.validate()
    if review.evidence_id != evidence.evidence_id:
        raise SchemaError("review evidence_id does not match evidence")
    raw = evidence.to_dict()
    protected = {"schema_version", "evidence_id", "source_spans", "created_by", "created_at"}
    forbidden = protected.intersection(review.field_corrections)
    if forbidden:
        raise SchemaError(f"review cannot edit immutable evidence fields: {sorted(forbidden)}")
    raw.update(copy.deepcopy(review.field_corrections))
    raw["review_status"] = review.decision
    return type(evidence).from_dict(raw)


def aggregate_learner_confusion(
    evidence: Iterable[LearnerConfusionEvidence],
    *,
    minimum_distinct_learners: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    groups: dict[tuple[str | None, str | None, str | None, str], list[LearnerConfusionEvidence]] = defaultdict(list)
    excluded: list[dict[str, str]] = []
    for item in evidence:
        item.validate()
        if item.solution_content_detected or detect_learner_solution(item.confusion_statement):
            excluded.append({"evidence_id": item.evidence_id, "reason": "solution_content"})
            continue
        key = (
            item.assessment_id,
            item.assessment_version,
            item.assessment_element_id,
            item.category,
        )
        groups[key].append(item)
    clusters: list[dict[str, Any]] = []
    for key, members in sorted(groups.items(), key=lambda pair: str(pair[0])):
        learners = {item.learner_pseudonym for item in members}
        if len(learners) < minimum_distinct_learners:
            excluded.extend(
                {"evidence_id": item.evidence_id, "reason": "below_distinct_learner_threshold"}
                for item in members
            )
            continue
        assessment_id, assessment_version, element_id, category = key
        severity = Counter(item.severity for item in members)
        cluster_id = stable_id(
            "confusion_cluster",
            {
                "key": key,
                "learners": sorted(learners),
                "evidence": sorted(item.evidence_id for item in members),
            },
        )
        clusters.append(
            {
                "schema_version": "learner-confusion-cluster/1",
                "cluster_id": cluster_id,
                "assessment_id": assessment_id,
                "assessment_version": assessment_version,
                "assessment_element_id": element_id,
                "category": category,
                "summary": _summarize_cluster(members),
                "distinct_learner_count": len(learners),
                "event_count": len(members),
                "severity_distribution": {
                    value: severity.get(value, 0)
                    for value in ("low", "medium", "high", "blocking")
                },
                "evidence_ids": sorted(item.evidence_id for item in members),
                "solution_leakage_check": "passed",
                "review_status": "pending",
            }
        )
    return clusters, excluded


def _summarize_cluster(members: list[LearnerConfusionEvidence]) -> str:
    needs = [item.proposed_clarity_need for item in members if item.proposed_clarity_need]
    if needs:
        return Counter(needs).most_common(1)[0][0]
    statements = [item.confusion_statement for item in members]
    return min(statements, key=len)[:500]


def build_evidence_bundle(
    *,
    domain_profile_id: str,
    target_scope: list[str],
    sme_evidence: Iterable[SMEEvidence],
    learner_clusters: Iterable[dict[str, Any]],
    split_manifest: str,
    review_manifest: str,
    excluded_evidence: list[dict[str, str]] | None = None,
    cutoff_at: str | None = None,
) -> EvidenceBundle:
    sme = list(sme_evidence)
    clusters = list(learner_clusters)
    for item in sme:
        item.validate()
        if item.review_status not in {"approved", "approved_with_edits"}:
            raise SchemaError(f"SME evidence {item.evidence_id} is not approved")
    for cluster in clusters:
        if cluster.get("review_status") not in {"approved", "approved_with_edits"}:
            raise SchemaError(f"learner cluster {cluster.get('cluster_id')} is not approved")
        if cluster.get("solution_leakage_check") != "passed":
            raise SchemaError("learner cluster failed solution leakage check")
    effective_cutoff = cutoff_at or utc_now()
    identity = {
        "domain_profile_id": domain_profile_id,
        "target_scope": target_scope,
        "sme_evidence_ids": sorted(item.evidence_id for item in sme),
        "learner_cluster_ids": sorted(str(item["cluster_id"]) for item in clusters),
        "cutoff_at": effective_cutoff,
    }
    bundle = EvidenceBundle(
        bundle_id=stable_id("bundle", identity),
        cutoff_at=effective_cutoff,
        domain_profile_id=domain_profile_id,
        target_scope=target_scope,
        sme_evidence_ids=identity["sme_evidence_ids"],
        learner_cluster_ids=identity["learner_cluster_ids"],
        excluded_evidence=excluded_evidence or [],
        split_manifest=split_manifest,
        review_manifest=review_manifest,
        statistics={
            "sme_positive_anchors": sum(
                item.category in {"positive_example", "accepted_choice"} for item in sme
            ),
            "sme_correction_pairs": sum(item.category == "correction_pair" for item in sme),
            "learner_confusion_clusters": len(clusters),
            "distinct_smes": 0,
            "distinct_learners": sum(int(row.get("distinct_learner_count", 0)) for row in clusters),
        },
    )
    raw = bundle.to_dict()
    raw["content_hash"] = ""
    bundle.content_hash = content_hash(raw)
    bundle.validate()
    return bundle
