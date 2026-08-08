"""Normalize a cloned assessment/GP triplet into one canonical AssessmentRecord.

Handles the three real-world source formats observed in the Nuvepro corpus:

* ``python_harness``  - a ``_Validation`` repo with ``test_cases.py`` exposing a
  ``TESTCASE_MARKS`` dict and ``add_milestone(...)`` phase grouping, or a
  simpler GP ``validation.py`` with ``testcase_*`` methods.
* ``json_testcases``  - ``_Main`` carrying ``test_cases.json`` + ``metadata.json``.
* ``doc_only``        - only the task markdown, with a "Testcases" / marks section.

Every parser fails soft: whatever cannot be extracted becomes a warning so the
record is still usable and data-quality issues stay visible.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .github_source import ClonedTriplet
from .schema import AssessmentRecord, Phase, TestCase, slugify, stable_id


# ---- small regex library --------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_MARKS = re.compile(r"\(\s*[Mm]arks?\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*\)")
_DURATION = re.compile(r"(\d+)\s*minutes", re.IGNORECASE)
_BOLD_NAME = re.compile(r"\*\*([A-Za-z0-9][A-Za-z0-9._/\-]{2,})\*\*")
_SERVICE = re.compile(r"\b(?:Amazon|AWS)\s+([A-Z][A-Za-z0-9 ]{1,40}?)(?=[,.\n(]| and | including)")


TASK_DOC_NAMES = (
    "Assessment-Activities.md",
    "Assessment_Activities.md",
    "Guided-Project-Activities.md",
    "Guided_Project_Activities.md",
)


def _find_task_doc(main_dir: Path) -> Path | None:
    for name in TASK_DOC_NAMES:
        p = main_dir / name
        if p.exists():
            return p
    # fallback: any *Activities*.md, else first top-level .md
    activities = sorted(main_dir.glob("*ctivities*.md"))
    if activities:
        return activities[0]
    top = sorted(main_dir.glob("*.md"))
    return top[0] if top else None


def _sections(md: str) -> dict[str, str]:
    lines = md.splitlines()
    out: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in lines:
        m = _HEADING.match(line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


_SERVICE_NOISE = {
    "assessment", "account", "account with all required permissions", "cli",
    "cloudformation template", "kms encryption", "console", "management console",
    "resources", "services", "sdk", "region",
}


def _extract_services(md: str) -> list[str]:
    found: list[str] = []
    for m in _SERVICE.finditer(md):
        name = re.sub(r"\s+", " ", m.group(1).strip().rstrip(".")).strip()
        low = name.lower()
        if low in _SERVICE_NOISE or low.startswith("account"):
            continue
        # drop trailing generic descriptors ("KMS encryption" -> "KMS")
        name = re.sub(r"\s+(encryption|template|service|services)$", "", name, flags=re.IGNORECASE).strip()
        if 2 <= len(name) <= 40 and name.lower() not in _SERVICE_NOISE and name not in found:
            found.append(name)
    return found[:40]


def _extract_resource_names(md: str) -> list[str]:
    names: list[str] = []
    for m in _BOLD_NAME.finditer(md):
        token = m.group(1).strip()
        # keep things that look like resource identifiers (contain - _ / . or lowercase-ids)
        if re.search(r"[-_/.]", token) and not token.endswith(":"):
            if token not in names:
                names.append(token)
    return names[:120]


def _parse_task_doc(md: str) -> dict[str, Any]:
    sections = _sections(md)
    # title = first level-1 heading
    title = ""
    for line in md.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2).strip()
            break
    scenario = sections.get("Scenario") or sections.get("Overview") or ""
    duration = None
    dm = _DURATION.search(md)
    if dm:
        duration = int(dm.group(1))
    # phases: headings that look like "Phase N ..." or "Task N ..."
    phases: list[Phase] = []
    phase_pat = re.compile(r"(?i)^(phase\s+\d+|task\s+\d+)\b[:\-\s]*(.*)$")
    for name, body in sections.items():
        clean = re.sub(r"\s+", " ", re.sub(r"[^\x00-\x7f]", "", name)).strip()  # drop emoji + collapse ws
        pm = phase_pat.match(clean)
        if pm:
            objective = ""
            osec = re.search(r"(?is)##?\s*Objective\s*(.+?)(?:\n#|\Z)", body)
            if osec:
                objective = osec.group(1).strip()[:400]
            tasks = re.findall(r"(?m)^\s*(?:\d+\.|[-*])\s+(.*)$", body)
            phases.append(Phase(name=clean, objective=objective, tasks=[t.strip()[:200] for t in tasks[:20]]))
    # doc-embedded testcases w/ marks: slice raw md from the Testcases heading
    # to the end (subsection phase headings would otherwise collide in `sections`).
    doc_testcases: list[TestCase] = []
    testcase_section = ""
    tc_head = re.search(r"(?im)^#{1,3}\s*test\s*cases?\s*$", md)
    if tc_head:
        testcase_section = md[tc_head.end():]
    if testcase_section:
        current_phase = ""
        for line in testcase_section.splitlines():
            ph = re.match(r"(?i)^#+\s*(phase\s+\d+.*)$", line.strip())
            if ph:
                current_phase = re.sub(r"\s+", " ", re.sub(r"[^\x00-\x7f]", "", ph.group(1))).strip()
                continue
            mm = _MARKS.search(line)
            if mm and ("-" in line or "*" in line or "Validate" in line):
                text = re.sub(r"^\s*[-*]\s*", "", line).strip()
                text = _MARKS.sub("", text).strip(" .*-")
                doc_testcases.append(
                    TestCase(
                        test_id=f"tc{len(doc_testcases) + 1:02d}",
                        name=text[:200],
                        marks=float(mm.group(1)),
                        phase=current_phase,
                        check_kind="doc",
                    )
                )
    return {
        "title": title,
        "scenario": scenario[:4000],
        "duration_minutes": duration,
        "services": _extract_services(md),
        "resource_registry": _extract_resource_names(md),
        "phases": phases,
        "doc_testcases": doc_testcases,
    }


def _parse_python_harness(text: str) -> dict[str, Any]:
    """Extract TESTCASE_MARKS + milestones + resource constants from test_cases.py."""
    result: dict[str, Any] = {"testcases": [], "phase_map": {}, "constants": []}
    marks: dict[str, float] = {}
    # TESTCASE_MARKS = { "name": 8, ... }
    block = re.search(r"TESTCASE_MARKS\s*=\s*\{(.*?)\}", text, re.DOTALL)
    if block:
        for m in re.finditer(r"[\"']([A-Za-z0-9_]+)[\"']\s*:\s*([0-9]+(?:\.[0-9]+)?)", block.group(1)):
            marks[m.group(1)] = float(m.group(2))
    # milestones: add_milestone("Phase X ...", [ "tcA", "tcB" ])
    phase_map: dict[str, str] = {}
    for m in re.finditer(r"add_milestone\(\s*[\"'](.+?)[\"']\s*,\s*\[(.*?)\]", text, re.DOTALL):
        phase = m.group(1).strip()
        for tc in re.finditer(r"[\"']([A-Za-z0-9_]+)[\"']", m.group(2)):
            phase_map[tc.group(1)] = phase
    # simpler GP harness: methods testcase_* with docstring/description
    method_names = re.findall(r"def\s+(testcase[_A-Za-z0-9]*)\s*\(", text)
    descriptions: dict[str, str] = {}
    for mm in re.finditer(r"def\s+(testcase[_A-Za-z0-9]*)\s*\([^)]*\):\s*(?:\n\s*[\"']{3}(.*?)[\"']{3}|\n\s*[a-z_]+\s*=\s*[\"'](.*?)[\"'])", text, re.DOTALL):
        name = mm.group(1)
        desc = (mm.group(2) or mm.group(3) or "").strip()
        if desc:
            descriptions[name] = re.sub(r"\s+", " ", desc)[:200]
    testcases: list[TestCase] = []
    names = list(marks.keys()) or method_names
    for i, name in enumerate(names, start=1):
        testcases.append(
            TestCase(
                test_id=f"tc{i:02d}",
                name=descriptions.get(name, name.replace("_", " ")),
                marks=marks.get(name, 0.0),
                phase=phase_map.get(name, ""),
                category=_infer_category(name),
                check_kind="python",
                details={"method": name},
            )
        )
    # constants that look like resource names
    consts: list[str] = []
    for m in re.finditer(r"^[A-Z0-9_]+\s*=\s*[\"']([A-Za-z0-9][A-Za-z0-9._/\-]{2,})[\"']", text, re.MULTILINE):
        val = m.group(1)
        if re.search(r"[-_/.]", val) and val not in consts:
            consts.append(val)
    result["testcases"] = testcases
    result["constants"] = consts[:120]
    return result


def _infer_category(name: str) -> str:
    low = name.lower()
    for key in ("cloudformation", "kms", "dynamodb", "s3", "ecs", "ecr", "codepipeline",
                "codedeploy", "codebuild", "cloudtrail", "cloudwatch", "cognito",
                "apigw", "api", "vpc", "iam", "lambda", "sns", "sqs", "secrets"):
        if key in low:
            return key
    return "general"


def _parse_json_testcases(testcases_raw: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    testcases: list[TestCase] = []
    items = testcases_raw if isinstance(testcases_raw, list) else testcases_raw.get("testCases", [])
    for i, tc in enumerate(items, start=1):
        testcases.append(
            TestCase(
                test_id=str(tc.get("id") or f"tc{i:02d}"),
                name=str(tc.get("name") or ""),
                marks=float(tc.get("marks") or 0),
                category=str(tc.get("category") or ""),
                check_kind="json",
                details={k: v for k, v in tc.items() if v is not None and k not in {"id", "name", "marks", "category"}},
            )
        )
    return {
        "testcases": testcases,
        "deliverables": metadata.get("deliverables", []),
        "technical_requirements": metadata.get("technical_requirements", []),
        "business_rules": metadata.get("business_rules", []),
        "tech_stack": metadata.get("tech_stack", {}),
    }


def normalize_triplet(triplet: ClonedTriplet) -> AssessmentRecord:
    warnings: list[str] = []
    parsed_doc: dict[str, Any] = {}
    main_files: list[str] = []
    grader_format = "none"
    testcases: list[TestCase] = []
    extra: dict[str, Any] = {}
    resource_registry: list[str] = []

    # ---- MAIN (task doc + optional structured json) ----
    if triplet.main_dir and triplet.main_dir.exists():
        main_files = [
            str(p.relative_to(triplet.main_dir))
            for p in sorted(triplet.main_dir.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        ]
        doc = _find_task_doc(triplet.main_dir)
        if doc:
            parsed_doc = _parse_task_doc(doc.read_text(encoding="utf-8", errors="replace"))
            resource_registry = parsed_doc.get("resource_registry", [])
        else:
            warnings.append("no task-doc markdown found in _Main")
        # structured json testcases in Main
        tc_json = triplet.main_dir / "test_cases.json"
        meta_json = triplet.main_dir / "metadata.json"
        if tc_json.exists():
            try:
                metadata = json.loads(meta_json.read_text(encoding="utf-8")) if meta_json.exists() else {}
                extra = _parse_json_testcases(json.loads(tc_json.read_text(encoding="utf-8")), metadata)
                testcases = extra["testcases"]
                grader_format = "json_testcases"
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"failed to parse test_cases.json: {exc}")
    else:
        warnings.append("missing _Main repo")

    # ---- VALIDATION (python harness) ----
    if triplet.validation_dir and triplet.validation_dir.exists():
        harness = triplet.validation_dir / "test_cases.py"
        if not harness.exists():
            harness = triplet.validation_dir / "validation.py"
        if harness.exists() and grader_format != "json_testcases":
            try:
                parsed = _parse_python_harness(harness.read_text(encoding="utf-8", errors="replace"))
                if parsed["testcases"]:
                    testcases = parsed["testcases"]
                    grader_format = "python_harness"
                    for c in parsed["constants"]:
                        if c not in resource_registry:
                            resource_registry.append(c)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"failed to parse python harness: {exc}")

    # ---- doc-embedded testcases as last resort ----
    if not testcases and parsed_doc.get("doc_testcases"):
        testcases = parsed_doc["doc_testcases"]
        grader_format = "doc_only"

    total_marks = round(sum(t.marks for t in testcases), 3)
    if testcases and total_marks == 0:
        warnings.append("testcases found but total marks = 0 (marks not parseable)")

    record = AssessmentRecord(
        record_id=stable_id("rec", {"base": triplet.base, "org": triplet.org}),
        base_repo=triplet.base,
        content_type=triplet.content_type,
        domain="aws",
        title=parsed_doc.get("title") or triplet.base,
        duration_minutes=parsed_doc.get("duration_minutes"),
        scenario=parsed_doc.get("scenario", ""),
        services=parsed_doc.get("services", []),
        phases=parsed_doc.get("phases", []),
        resource_registry=resource_registry,
        testcases=testcases,
        total_marks=total_marks,
        grader_format=grader_format,
        deliverables=extra.get("deliverables", []),
        technical_requirements=extra.get("technical_requirements", []),
        business_rules=extra.get("business_rules", []),
        tech_stack=extra.get("tech_stack", {}),
        has_solution=bool(triplet.solution_dir and triplet.solution_dir.exists()),
        has_validation=bool(triplet.validation_dir and triplet.validation_dir.exists()),
        main_files=main_files,
        warnings=warnings,
        source={
            "org": triplet.org,
            "base_repo": triplet.base,
            "missing_members": triplet.missing,
        },
    )
    return record.finalize()
