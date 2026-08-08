"""Build a house-style Template from one or more normalized records.

The template is fully deterministic: it aggregates observable conventions
(file layout, phase counts, marks totals, testcase categories, naming style,
grader formats) across the supplied records. No model is required. It becomes
the reviewable/approvable blueprint the skill compiler renders against.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Iterable

from .schema import AssessmentRecord, Template, slugify, stable_id, utc_now


def _naming_style(names: Iterable[str]) -> dict[str, object]:
    names = [n for n in names if n]
    kebab = sum(1 for n in names if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", n))
    slash = sum(1 for n in names if "/" in n)
    prefixes = Counter(n.split("-")[0] for n in names if "-" in n)
    return {
        "total_sampled": len(names),
        "kebab_case_fraction": round(kebab / len(names), 3) if names else 0,
        "path_style_fraction": round(slash / len(names), 3) if names else 0,
        "common_prefixes": [p for p, _ in prefixes.most_common(8)],
        "examples": names[:15],
    }


def build_template(
    records: list[AssessmentRecord],
    *,
    name: str,
    content_type: str = "assessment",
    domain: str = "aws",
) -> Template:
    if not records:
        raise ValueError("at least one record is required to build a template")

    all_services = Counter(s for r in records for s in r.services)
    all_categories = Counter(t.category for r in records for t in r.testcases if t.category)
    grader_formats = Counter(r.grader_format for r in records)
    phase_counts = [len(r.phases) for r in records if r.phases]
    testcase_counts = [len(r.testcases) for r in records if r.testcases]
    totals = [r.total_marks for r in records if r.total_marks]
    durations = [r.duration_minutes for r in records if r.duration_minutes]
    all_resources = [n for r in records for n in r.resource_registry]

    # pick the richest record (most testcases + has structured metadata) as canonical example
    canonical = max(
        records,
        key=lambda r: (len(r.testcases), bool(r.deliverables), r.total_marks),
    )

    structure = {
        "required_main_files": _common_main_files(records),
        "task_doc_names_seen": sorted({_task_doc_name(r) for r in records if _task_doc_name(r)}),
        "grader_formats_seen": dict(grader_formats),
        "recommended_grader_format": grader_formats.most_common(1)[0][0] if grader_formats else "python_harness",
        "triplet_completeness": {
            "with_solution": sum(1 for r in records if r.has_solution),
            "with_validation": sum(1 for r in records if r.has_validation),
            "total": len(records),
        },
        "learner_safe_vs_evaluator_only": {
            "learner_safe": ["_Main task doc, starter code, images"],
            "evaluator_only": ["_Solution reference answer", "_Validation grader + expected values"],
            "rule": "Never place solution code, answer keys, or grader expected values into _Main.",
        },
    }

    house_style = {
        "phase_count": {
            "min": min(phase_counts) if phase_counts else 0,
            "median": int(median(phase_counts)) if phase_counts else 0,
            "max": max(phase_counts) if phase_counts else 0,
        },
        "testcase_count": {
            "min": min(testcase_counts) if testcase_counts else 0,
            "median": int(median(testcase_counts)) if testcase_counts else 0,
            "max": max(testcase_counts) if testcase_counts else 0,
        },
        "total_marks": {
            "values": sorted(set(int(t) for t in totals)),
            "default": int(median(totals)) if totals else (100 if content_type == "assessment" else 0),
        },
        "duration_minutes": {
            "values": sorted(set(durations)),
            "default": int(median(durations)) if durations else None,
        },
        "top_services": [s for s, _ in all_services.most_common(20)],
        "testcase_categories": [c for c, _ in all_categories.most_common(20)],
        "resource_naming": _naming_style(all_resources),
        "exact_name_discipline": (
            "Resource names stated in the task doc MUST match, byte-for-byte, the "
            "names checked by the grader. No extra spaces or case differences."
        ),
    }

    testcase_schema = {
        "fields": {
            "id": "stable id, e.g. TC001 or tc01",
            "name": "human-readable check title",
            "category": "grouping tag (service or capability)",
            "marks": "positive number; all marks sum to total_marks",
            "phase": "the phase/milestone this check belongs to",
            "check_kind": "api | resource | db | code | e2e",
            "details": "format-specific fields (endpoint, expectedStatusCode, resourceName, expectedValues...)",
        },
        "grouping": "testcases are grouped into phases/milestones matching the task doc",
        "marks_rule": "sum(testcase.marks) == total_marks",
    }

    template = Template(
        template_id=stable_id(
            "tpl",
            {"name": name, "records": sorted(r.record_id for r in records), "time": utc_now()},
        ),
        name=name,
        domain=domain,
        content_type=content_type,
        status="ready",
        structure=structure,
        house_style=house_style,
        testcase_schema=testcase_schema,
        derived_from=[r.record_id for r in records],
        canonical_example={
            "record_id": canonical.record_id,
            "title": canonical.title,
            "base_repo": canonical.base_repo,
            "total_marks": canonical.total_marks,
            "grader_format": canonical.grader_format,
            "phase_names": [p.name for p in canonical.phases],
            "testcase_categories": sorted({t.category for t in canonical.testcases if t.category}),
        },
    )
    return template.finalize()


def _task_doc_name(record: AssessmentRecord) -> str:
    for f in record.main_files:
        if re.search(r"(?i)(activities)\.md$", f):
            return f.split("/")[-1]
    return ""


def _common_main_files(records: list[AssessmentRecord]) -> list[str]:
    """Top-level file kinds that appear in most _Main repos."""
    kinds: Counter[str] = Counter()
    for r in records:
        seen = set()
        for f in r.main_files:
            top = f.split("/")[0]
            kind = _classify_file(top, f)
            if kind not in seen:
                kinds[kind] += 1
                seen.add(kind)
    threshold = max(1, len(records) // 2)
    return [k for k, c in kinds.most_common() if c >= threshold]


def _classify_file(top: str, full: str) -> str:
    low = full.lower()
    if low.endswith("activities.md"):
        return "task-doc (Activities.md)"
    if "checklist" in low:
        return "resource checklist"
    if low.endswith(".yaml") or low.endswith(".yml"):
        if "cloudformation" in low or "template" in low:
            return "cloudformation template"
        return "config yaml"
    if low.endswith(".json") and ("test_cases" in low or "metadata" in low):
        return "structured testcases/metadata json"
    if top.lower() in {"images", "image"}:
        return "images"
    if low.endswith((".java", ".py", ".js", ".ts")):
        return "starter code project"
    return f"other ({top})"
