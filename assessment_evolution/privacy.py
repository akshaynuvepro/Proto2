"""Privacy and learner-solution boundaries applied before model or telemetry use."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from .schemas import ConversationRecord, content_hash, stable_id, utc_now


PRIVACY_POLICY_VERSION = "assessment-redaction-policy/1"


@dataclass(frozen=True, slots=True)
class Detection:
    label: str
    start: int
    end: int
    replacement: str
    confidence: float = 1.0


@dataclass(slots=True)
class RedactionReport:
    schema_version: str = "redaction-report/1"
    report_id: str = ""
    conversation_id: str = ""
    policy_version: str = PRIVACY_POLICY_VERSION
    detections: list[dict[str, Any]] = field(default_factory=list)
    telemetry_allowed: bool = True
    optimizer_allowed: bool = True
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "conversation_id": self.conversation_id,
            "policy_version": self.policy_version,
            "detections": self.detections,
            "telemetry_allowed": self.telemetry_allowed,
            "optimizer_allowed": self.optimizer_allowed,
            "created_at": self.created_at,
        }


_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "secret.credential",
        re.compile(
            r"(?i)\b(?:aws_access_key_id|aws_secret_access_key|api[_ -]?key|access[_ -]?token|password)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_.=-]{8,}"
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "secret.credential",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        "pii.direct",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "pii.direct",
        re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{8,}\d)(?!\d)"),
        "[REDACTED_PHONE]",
    ),
    (
        "internal.restricted",
        re.compile(r"\b\d{12}\b"),
        "[PSEUDONYMIZED_ACCOUNT]",
    ),
]

_SOLUTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "learner.hint_request",
        re.compile(
            r"(?i)\b(?:give|tell|show)\s+me\s+(?:the\s+)?(?:answer|solution|hint|next step)\b"
        ),
    ),
    (
        "learner.hint_request",
        re.compile(r"(?i)\b(?:what|which)\s+(?:is|option is)\s+(?:the\s+)?correct\b"),
    ),
    (
        "learner.solution_strategy",
        re.compile(
            r"(?i)\b(?:how do i|how to|steps? to|command to|code to|solve this|complete this)\b"
        ),
    ),
    (
        "learner.code",
        re.compile(
            r"(?is)(?:```[\w+-]*\s*\n.+?```|"
            r"\b(?:aws|kubectl|terraform|python|curl)\s+[-\w].*)"
        ),
    ),
    (
        "learner.solution",
        re.compile(
            r"(?i)\b(?:my answer is|i chose|the answer should be|i solved it by|i configured)\b"
        ),
    ),
]

_UNDERSTANDING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("expected_output_unclear", re.compile(r"(?i)\b(?:submit|expected output|output format|deliverable|screenshot)\b")),
    ("undefined_terminology", re.compile(r"(?i)\b(?:what does|term|meaning|define|unclear word)\b")),
    ("assessment_scope_unclear", re.compile(r"(?i)\b(?:in scope|out of scope|how much|which parts?|scope)\b")),
    ("environment_or_tool_confusion", re.compile(r"(?i)\b(?:environment|console|portal|workspace|tool|where do i)\b")),
    ("navigation_confusion", re.compile(r"(?i)\b(?:navigate|page|screen|section|find the assessment)\b")),
    ("prerequisite_not_communicated", re.compile(r"(?i)\b(?:prerequisite|before starting|access required|need an account)\b")),
    ("feedback_unclear", re.compile(r"(?i)\b(?:feedback|why was|score says|marked wrong)\b")),
    ("conflicting_requirements", re.compile(r"(?i)\b(?:conflict|contradict|one place says|but the instruction)\b")),
    ("example_or_format_mismatch", re.compile(r"(?i)\b(?:example.*format|format.*example|does not match)\b")),
    ("instruction_ambiguity", re.compile(r"(?i)\b(?:instruction|asks? me|not clear|ambiguous|what am i supposed)\b")),
]


def detect_privacy(text: str) -> list[Detection]:
    detections: list[Detection] = []
    for label, pattern, replacement in _PATTERNS:
        for match in pattern.finditer(text):
            detections.append(Detection(label, match.start(), match.end(), replacement))
    return _non_overlapping(detections)


def detect_learner_solution(text: str) -> list[Detection]:
    detections = []
    for label, pattern in _SOLUTION_PATTERNS:
        for match in pattern.finditer(text):
            detections.append(
                Detection(label, match.start(), match.end(), f"[{label.upper().replace('.', '_')}]")
            )
    return _non_overlapping(detections)


def _non_overlapping(detections: list[Detection]) -> list[Detection]:
    ordered = sorted(detections, key=lambda item: (item.start, -(item.end - item.start)))
    out: list[Detection] = []
    last_end = -1
    for item in ordered:
        if item.start >= last_end:
            out.append(item)
            last_end = item.end
    return out


def apply_detections(text: str, detections: list[Detection]) -> str:
    result = text
    for item in sorted(detections, key=lambda value: value.start, reverse=True):
        result = result[: item.start] + item.replacement + result[item.end :]
    return result


def classify_learner_span(text: str) -> tuple[str, str | None, list[str]]:
    """Return boundary class, allowed confusion category, and safety labels."""
    solution = detect_learner_solution(text)
    matched_categories = [
        category for category, pattern in _UNDERSTANDING_PATTERNS if pattern.search(text)
    ]
    if solution and matched_categories:
        return "mixed", matched_categories[0], sorted({row.label for row in solution})
    if solution:
        return "solution_seeking", None, sorted({row.label for row in solution})
    if matched_categories:
        return "assessment_understanding", matched_categories[0], []
    return "irrelevant", None, []


def sanitize_conversation(
    record: ConversationRecord,
) -> tuple[ConversationRecord, RedactionReport]:
    record.validate()
    sanitized = ConversationRecord.from_dict(record.to_dict())
    detection_rows: list[dict[str, Any]] = []
    solution_found = False
    for message in sanitized.messages:
        detections = detect_privacy(message["content"])
        if record.persona in {"learner", "mixed"} and message["speaker_persona"] == "learner":
            learner_detections = detect_learner_solution(message["content"])
            detections = _non_overlapping(detections + learner_detections)
            solution_found = solution_found or bool(learner_detections)
        original_hash = message["content_hash"]
        message["content"] = apply_detections(message["content"], detections)
        message["content_hash"] = content_hash(message["content"])
        message["redaction_state"] = "sanitized"
        for detection in detections:
            detection_rows.append(
                {
                    "message_id": message["message_id"],
                    "label": detection.label,
                    "start_char": detection.start,
                    "end_char": detection.end,
                    "source_text_hash": original_hash,
                    "confidence": detection.confidence,
                }
            )
    report = RedactionReport(
        report_id=stable_id(
            "redaction",
            {"conversation_id": record.conversation_id, "detections": detection_rows},
        ),
        conversation_id=record.conversation_id,
        detections=detection_rows,
        optimizer_allowed=not solution_found,
    )
    sanitized.metadata = {
        **copy.deepcopy(sanitized.metadata),
        "redaction_report_id": report.report_id,
        "redaction_policy_version": report.policy_version,
        "optimizer_allowed": report.optimizer_allowed,
        "solution_boundary": "passed" if report.optimizer_allowed else "quarantined",
    }
    sanitized.validate()
    return sanitized, report


def telemetry_safe(value: Any) -> bool:
    """Fail closed when provider-bound telemetry still looks sensitive."""
    text = value if isinstance(value, str) else str(value)
    return not detect_privacy(text) and not detect_learner_solution(text)
