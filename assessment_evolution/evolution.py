"""Target skill patching and deterministic evolution hard gates."""

from __future__ import annotations

import copy
import difflib
import re
from typing import Any, Iterable

from .privacy import detect_learner_solution, detect_privacy
from .schemas import (
    EvolutionResult,
    SchemaError,
    TargetSkillEnvelope,
    content_hash,
)


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def markdown_sections(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines(keepends=True)
    starts: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line.rstrip("\r\n"))
        if match:
            starts.append((index, len(match.group(1)), match.group(2)))
    sections: dict[str, str] = {}
    for position, (start, level, title) in enumerate(starts):
        end = len(lines)
        for later_start, later_level, _ in starts[position + 1 :]:
            if later_level <= level:
                end = later_start
                break
        sections[title] = "".join(lines[start:end])
    return sections


def parse_frontmatter(markdown: str) -> dict[str, str]:
    text = markdown.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip('"')
    return values


def make_patch(
    original: str,
    evolved: str,
    *,
    evidence_ids: Iterable[str],
    principle_ids: Iterable[str] = (),
    rationale: str,
    expected_effect: str,
) -> list[dict[str, Any]]:
    """Build reversible line operations whose reverse-order application is exact."""
    before_lines = original.splitlines(keepends=True)
    after_lines = evolved.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    operations: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = "".join(before_lines[i1:i2]) or None
        after = "".join(after_lines[j1:j2]) or None
        operation = {"insert": "add", "delete": "remove", "replace": "replace"}[tag]
        section = _section_at_line(before_lines, i1)
        operations.append(
            {
                "operation_id": f"op_{len(operations) + 1:03d}",
                "operation": operation,
                "target": {
                    "section": section,
                    "line_start": i1,
                    "line_end": i2,
                    "anchor": _anchor(before_lines, i1),
                },
                "before_hash": content_hash(before) if before is not None else None,
                "after_hash": content_hash(after) if after is not None else None,
                "before": before,
                "after": after,
                "rationale": rationale,
                "evidence_ids": sorted(set(evidence_ids)),
                "principle_ids": sorted(set(principle_ids)),
                "expected_effect": expected_effect,
                "risk": "low",
                "reversible": True,
            }
        )
    return operations


def _section_at_line(lines: list[str], index: int) -> str:
    for line in reversed(lines[: index + 1]):
        match = _HEADING.match(line.rstrip("\r\n"))
        if match:
            return match.group(2)
    return "frontmatter"


def _anchor(lines: list[str], index: int) -> str | None:
    if index > 0:
        return lines[index - 1].rstrip("\r\n")[:200]
    return None


def apply_patch(original: str, operations: Iterable[dict[str, Any]]) -> str:
    supplied = list(operations)
    if any(
        "line_start" not in (operation.get("target") or {})
        for operation in supplied
    ):
        return _apply_anchored_patch(original, supplied)
    lines = original.splitlines(keepends=True)
    rows = sorted(
        supplied,
        key=lambda item: int((item.get("target") or {}).get("line_start", -1)),
        reverse=True,
    )
    for operation in rows:
        kind = operation.get("operation")
        if kind not in {"add", "replace", "remove"}:
            raise SchemaError(f"unsupported deterministic patch operation {kind!r}")
        target = operation.get("target") or {}
        start = int(target.get("line_start", -1))
        end = int(target.get("line_end", -1))
        if start < 0 or end < start or end > len(lines):
            raise SchemaError(f"invalid patch line range {start}:{end}")
        current = "".join(lines[start:end]) or None
        if current != operation.get("before"):
            raise SchemaError(f"patch before content mismatch for {operation.get('operation_id')}")
        if (content_hash(current) if current is not None else None) != operation.get("before_hash"):
            raise SchemaError(f"patch before hash mismatch for {operation.get('operation_id')}")
        replacement = operation.get("after")
        if (content_hash(replacement) if replacement is not None else None) != operation.get("after_hash"):
            raise SchemaError(f"patch after hash mismatch for {operation.get('operation_id')}")
        lines[start:end] = replacement.splitlines(keepends=True) if replacement is not None else []
    return "".join(lines)


def _apply_anchored_patch(original: str, operations: list[dict[str, Any]]) -> str:
    """Apply model-authored exact-content operations using stable anchors."""
    result = original
    for operation in operations:
        kind = operation.get("operation")
        before = operation.get("before")
        after = operation.get("after")
        if (content_hash(before) if before is not None else None) != operation.get("before_hash"):
            raise SchemaError(f"patch before hash mismatch for {operation.get('operation_id')}")
        if (content_hash(after) if after is not None else None) != operation.get("after_hash"):
            raise SchemaError(f"patch after hash mismatch for {operation.get('operation_id')}")
        if kind in {"replace", "remove", "move"}:
            if not before or result.count(before) != 1:
                raise SchemaError(
                    f"patch before content must occur exactly once for {operation.get('operation_id')}"
                )
            result = result.replace(before, after if kind == "replace" else "", 1)
        if kind in {"add", "move"}:
            insertion = after if kind == "add" else before
            if insertion is None:
                raise SchemaError(f"{kind} requires insertion content")
            anchor = str((operation.get("target") or {}).get("anchor") or "")
            if not anchor or result.count(anchor) != 1:
                raise SchemaError(
                    f"patch anchor must occur exactly once for {operation.get('operation_id')}"
                )
            position = result.index(anchor) + len(anchor)
            result = result[:position] + insertion + result[position:]
        if kind not in {"add", "replace", "remove", "move"}:
            raise SchemaError(f"unsupported patch operation {kind!r}")
    return result


def validate_target_contract(
    envelope: TargetSkillEnvelope,
    evolved: str,
) -> dict[str, bool]:
    envelope.validate()
    original = envelope.exact_skill_markdown
    original_frontmatter = parse_frontmatter(original)
    evolved_frontmatter = parse_frontmatter(evolved)
    required_frontmatter = True
    for key, rule in envelope.required_frontmatter.items():
        if key not in evolved_frontmatter:
            required_frontmatter = False
            continue
        if rule.get("immutable") and evolved_frontmatter.get(key) != original_frontmatter.get(key):
            required_frontmatter = False
    original_sections = markdown_sections(original)
    evolved_sections = markdown_sections(evolved)
    immutable_ok = True
    for section, expected_hash in envelope.immutable_sections.items():
        original_value = original_sections.get(section)
        evolved_value = evolved_sections.get(section)
        if (
            original_value is None
            or evolved_value != original_value
            or content_hash(original_value) != expected_hash
        ):
            immutable_ok = False
    required_sections = all(section in evolved_sections for section in envelope.required_sections)
    tools_preserved = all(
        str(contract.get("tool_id") or contract.get("id") or contract.get("tool") or "") in evolved
        for contract in envelope.tool_contracts
        if contract.get("required", True)
    )
    scripts_preserved = all(
        str(contract.get("script") or contract.get("id") or "") in evolved
        for contract in envelope.script_contracts
        if contract.get("required", True)
    )
    return {
        "required_frontmatter_preserved": required_frontmatter,
        "immutable_sections_preserved": immutable_ok,
        "required_sections_present": required_sections,
        "tool_contracts_preserved": tools_preserved,
        "script_contracts_preserved": scripts_preserved,
        "output_contracts_preserved": _output_contract_preserved(envelope, evolved),
    }


def _output_contract_preserved(envelope: TargetSkillEnvelope, evolved: str) -> bool:
    required_literals = envelope.output_contract.get("required_literals") or []
    return all(str(literal) in evolved for literal in required_literals)


def validate_evolution(
    result: EvolutionResult,
    envelope: TargetSkillEnvelope,
    *,
    approved_evidence_ids: Iterable[str],
) -> dict[str, bool]:
    result.validate()
    envelope.validate()
    approved = set(approved_evidence_ids)
    evolved = result.evolved_skill_markdown
    contract = validate_target_contract(envelope, evolved)
    patch_reconstructs = False
    try:
        patch_reconstructs = apply_patch(envelope.exact_skill_markdown, result.patch) == evolved
    except SchemaError:
        patch_reconstructs = False
    evidence_grounded = all(
        bool(operation.get("evidence_ids"))
        and set(operation.get("evidence_ids") or []).issubset(approved)
        for operation in result.patch
    )
    solution_leakage = bool(detect_learner_solution(evolved))
    privacy_leakage = bool(detect_privacy(evolved))
    input_matches = result.target_skill.get("input_hash") == envelope.input_content_hash
    permitted = set(envelope.permitted_change_areas)
    changes_permitted = all(
        not permitted or str((operation.get("target") or {}).get("section") or "") in permitted
        for operation in result.patch
    )
    changed_lines = sum(
        len(str(operation.get("before") or "").splitlines())
        + len(str(operation.get("after") or "").splitlines())
        for operation in result.patch
    )
    change_budget = int(envelope.metadata.get("change_budget_lines", 0) or 0)
    return {
        "schema_valid": True,
        "target_input_matches": input_matches,
        "patch_reconstructs_output": patch_reconstructs,
        "immutable_sections_preserved": contract["immutable_sections_preserved"],
        "required_frontmatter_preserved": contract["required_frontmatter_preserved"],
        "required_sections_present": contract["required_sections_present"],
        "tool_contracts_preserved": contract["tool_contracts_preserved"],
        "script_contracts_preserved": contract["script_contracts_preserved"],
        "output_contracts_preserved": contract["output_contracts_preserved"],
        "all_changes_evidence_grounded": evidence_grounded,
        "changes_within_permitted_areas": changes_permitted,
        "change_budget_respected": not change_budget or changed_lines <= change_budget,
        "learner_solution_leakage_detected": solution_leakage,
        "privacy_leakage_detected": privacy_leakage,
    }


def evolution_from_model(
    raw: dict[str, Any],
    *,
    envelope: TargetSkillEnvelope,
    approved_evidence_ids: Iterable[str],
) -> tuple[EvolutionResult, dict[str, bool]]:
    """Parse model JSON, recompute gates, and fail closed on unsafe output."""
    result = EvolutionResult.from_dict(copy.deepcopy(raw))
    gates = validate_evolution(
        result, envelope, approved_evidence_ids=approved_evidence_ids
    )
    critical = {
        key: value
        for key, value in gates.items()
        if key
        not in {
            "learner_solution_leakage_detected",
            "privacy_leakage_detected",
        }
    }
    passed = all(critical.values()) and not gates["learner_solution_leakage_detected"] and not gates["privacy_leakage_detected"]
    if result.decision == "update" and not passed:
        safe_original = envelope.exact_skill_markdown
        result = EvolutionResult(
            decision="needs_review",
            summary="Candidate failed deterministic evolution gates and was quarantined.",
            target_skill={
                "skill_id": envelope.target_skill_id,
                "input_version": envelope.input_version,
                "input_hash": envelope.input_content_hash,
                "output_version_proposal": envelope.input_version,
                "output_hash": content_hash(safe_original),
            },
            evolved_skill_markdown=safe_original,
            patch=[],
            evidence_coverage=result.evidence_coverage,
            preserved_contracts=result.preserved_contracts,
            learner_clarity_actions=[],
            validation=gates,
            risks=[
                {
                    "severity": "high",
                    "description": "One or more deterministic evolution gates failed.",
                    "mitigation": "Review the failed gates and produce a new proposal.",
                    "requires_sme_review": True,
                }
            ],
            uncertainties=[
                key
                for key, value in gates.items()
                if (value if key.endswith("_detected") else not value)
            ],
            recommended_review_focus=[
                key
                for key, value in gates.items()
                if (value if key.endswith("_detected") else not value)
            ],
        )
        result.validate()
    else:
        result.validation = {**result.validation, **gates}
    return result, gates


def no_change_result(
    envelope: TargetSkillEnvelope,
    *,
    evidence_ids: Iterable[str],
    summary: str,
) -> EvolutionResult:
    result = EvolutionResult(
        decision="no_change",
        summary=summary,
        target_skill={
            "skill_id": envelope.target_skill_id,
            "input_version": envelope.input_version,
            "input_hash": envelope.input_content_hash,
            "output_version_proposal": envelope.input_version,
            "output_hash": envelope.input_content_hash,
        },
        evolved_skill_markdown=envelope.exact_skill_markdown,
        patch=[],
        evidence_coverage=[
            {
                "evidence_id": evidence_id,
                "disposition": "already_satisfied",
                "operation_ids": [],
                "reason": summary,
            }
            for evidence_id in evidence_ids
        ],
        validation={
            "schema_valid": True,
            "patch_reconstructs_output": True,
            "immutable_sections_preserved": True,
            "required_sections_present": True,
            "tool_contracts_preserved": True,
            "output_contracts_preserved": True,
            "all_changes_evidence_grounded": True,
            "domain_claims_grounded": True,
            "learner_solution_leakage_detected": False,
            "change_budget_respected": True,
        },
    )
    result.validate()
    return result
