"""Compile an approved Template into a STRUCTURED SKILL PACKAGE (multiple files).

The package an agent consumes to author a full assessment:

    SKILL.md                          router: overview + workflow + hard rules
    references/house-style.md         services, marks/phase norms, naming discipline
    references/main-repo.md           how to build _Main (learner-facing)
    references/solution-repo.md       how to build _Solution (evaluator-only)
    references/validation-repo.md     how to build _Validation grader
    references/testcase-and-marks.md  testcase schema + consistency contract
    scripts/check_consistency.py      deterministic validator for a generated set

Two builders produce the SAME file set:
- ``compile_skill``            deterministic, offline (no model)
- ``compile_skill_with_model`` LLM-authored, richer prose (needs OpenRouter/OpenAI)
"""

from __future__ import annotations

import json
from typing import Any

from .llm import ModelSettings, generate_text, strip_code_fence
from .schema import AssessmentRecord, SkillFile, Template, slugify, stable_id, utc_now


# ---- file plan -----------------------------------------------------------

FILE_PLAN: list[tuple[str, str, str]] = [
    ("SKILL.md", "router",
     "Router/overview skill: what this authors, when to use it, the ordered workflow, "
     "the three output repos, a summary of the hard rules, and pointers to each reference file."),
    ("references/house-style.md", "house_style",
     "The Nuvepro TLS house style: common AWS services, testcase categories, typical phase count, "
     "total-marks and duration norms, required _Main files, and the exact resource-naming discipline."),
    ("references/main-repo.md", "main_repo",
     "How to build the _Main repo (learner-facing): the file tree, the Assessment-Activities.md "
     "skeleton with all required sections, phases with exact resource names, and the learner-safe rule."),
    ("references/solution-repo.md", "solution_repo",
     "How to build the _Solution repo (evaluator-only): mirror the _Main starter project with all "
     "TODOs completed so it passes every testcase; never expose it to the learner."),
    ("references/validation-repo.md", "validation_repo",
     "How to build the _Validation grader in the recommended format: the file set, one check per task "
     "bullet, marks per check, phase/milestone grouping, and the result JSON."),
    ("references/testcase-and-marks.md", "testcase_marks",
     "The structured testcase schema, the marks rule (sum == total), and the full task<->grader<->marks "
     "consistency contract."),
]


# ---- shared context ------------------------------------------------------

def _context(template: Template, example: AssessmentRecord | None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "domain": template.domain,
        "content_type": template.content_type,
        "structure": template.structure,
        "house_style": template.house_style,
        "testcase_schema": template.testcase_schema,
        "canonical_example_summary": template.canonical_example,
    }
    if example is not None:
        ctx["worked_example"] = {
            "title": example.title,
            "scenario": example.scenario[:1500],
            "duration_minutes": example.duration_minutes,
            "total_marks": example.total_marks,
            "grader_format": example.grader_format,
            "services": example.services,
            "resource_registry": example.resource_registry[:40],
            "phases": [{"name": p.name, "objective": p.objective, "tasks": p.tasks[:6]} for p in example.phases],
            "testcases": [{"id": t.test_id, "name": t.name, "marks": t.marks,
                           "category": t.category, "phase": t.phase} for t in example.testcases],
            "main_files": example.main_files[:60],
            "tech_stack": example.tech_stack,
        }
    return ctx


def _front_matter(template: Template, name: str) -> dict[str, str]:
    return {
        "name": name,
        "description": (
            f"Authors complete Nuvepro {template.domain.upper()} "
            f"{template.content_type.replace('_', ' ')} repositories "
            f"(_Main/_Solution/_Validation) in TLS house style."
        ),
        "version": "1",
        "domain": template.domain,
        "content_type": template.content_type,
        "template_id": template.template_id,
        "template_hash": template.content_hash,
    }


def _fm_block(fm: dict[str, str]) -> str:
    return "---\n" + "\n".join(f'{k}: "{v}"' for k, v in fm.items()) + "\n---\n"


def _bullet(items: list[Any], empty: str = "_none observed_") -> str:
    items = [str(i) for i in items if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else empty


CHECK_SCRIPT = '''#!/usr/bin/env python3
"""Deterministic consistency checker for a generated assessment set.

Usage:
    python check_consistency.py <path-to-generated-assessment-dir>

Expects, inside the directory:
    Main/Assessment-Activities.md   (or Guided-Project-Activities.md)
    test_cases.json                 (list of {id,name,marks,category,phase})

Checks:
    1. testcase marks sum to the declared total (from --total or doc).
    2. every phase in the doc has >= 1 testcase.
    3. exact resource names checked appear in the task doc.
    4. no obvious solution/answer-key leakage in the learner-facing doc.
Exit code 0 = all pass, 1 = failures found.
"""
import json, re, sys
from pathlib import Path

def main(root):
    root = Path(root)
    problems = []
    doc = next((p for p in root.rglob("*ctivities*.md")), None)
    if not doc:
        print("FAIL: no Activities.md task document found"); return 1
    text = doc.read_text(encoding="utf-8", errors="replace")

    tc_path = next((p for p in root.rglob("test_cases.json")), None)
    testcases = []
    if tc_path:
        raw = json.loads(tc_path.read_text(encoding="utf-8"))
        testcases = raw.get("testCases", raw) if isinstance(raw, dict) else raw

    total_marks = sum(float(t.get("marks", 0)) for t in testcases)
    doc_total = None
    m = re.search(r"Total\\s+Marks?\\s*[:=]?\\s*(\\d+)", text, re.IGNORECASE)
    if m:
        doc_total = float(m.group(1))
    if doc_total is not None and abs(doc_total - total_marks) > 0.001:
        problems.append(f"marks mismatch: testcases sum {total_marks} != doc total {doc_total}")

    doc_phases = set(re.findall(r"(?im)^#\\s*(Phase\\s+\\d+)", text))
    tc_phases = {str(t.get("phase","")).split("-")[0].strip() for t in testcases if t.get("phase")}
    for ph in doc_phases:
        if not any(ph.lower() in p.lower() for p in tc_phases):
            problems.append(f"phase '{ph}' in doc has no testcase")

    for t in testcases:
        rn = (t.get("details") or {}).get("resourceName") or (t.get("details") or {}).get("expectedName")
        if rn and str(rn) not in text:
            problems.append(f"resource '{rn}' checked by grader not present in task doc")

    for leak in ["THE-ANSWER-IS", "answer_key", "solution:"]:
        if leak.lower() in text.lower():
            problems.append(f"possible solution leakage in learner doc: '{leak}'")

    if problems:
        print("CONSISTENCY: FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"CONSISTENCY: PASS ({len(testcases)} testcases, {total_marks} marks)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
'''


# ---- deterministic package -----------------------------------------------

def _det_file(key: str, template: Template, example: AssessmentRecord | None, fm: dict[str, str]) -> str:
    hs, st, ts, ex = template.house_style, template.structure, template.testcase_schema, template.canonical_example
    ct = template.content_type.replace("_", " ")
    total = (hs.get("total_marks") or {}).get("default")
    grader = st.get("recommended_grader_format", "python_harness")

    if key == "router":
        return (
            _fm_block(fm)
            + f"# {fm['name']}\n\n"
            f"## Mission\n\nAuthor a complete Nuvepro {template.domain.upper()} {ct} as three linked repos: "
            f"`<base>_Main` (learner-facing), `<base>_Solution` (evaluator-only reference), and "
            f"`<base>_Validation` (evaluator-only grader).\n\n"
            "## When to use\n\nUse this skill when asked to create a new AWS "
            f"{ct} from a brief (scenario + objectives + level).\n\n"
            "## Workflow\n\n"
            "1. Read `references/house-style.md` to lock the conventions.\n"
            "2. Draft `_Main` per `references/main-repo.md` (task doc + starter project).\n"
            "3. Define testcases + marks per `references/testcase-and-marks.md`.\n"
            "4. Build `_Solution` per `references/solution-repo.md`.\n"
            "5. Build `_Validation` per `references/validation-repo.md` "
            f"(recommended format: `{grader}`).\n"
            "6. Run `scripts/check_consistency.py <dir>` and fix every reported issue.\n\n"
            "## Hard rules (non-negotiable)\n\n"
            f"- Total marks MUST equal **{total}** (sum of all testcase marks).\n"
            "- Exact resource names in the task doc MUST match the grader byte-for-byte.\n"
            "- NEVER put solution code, answer keys, or grader expected-values into `_Main`.\n"
            "- Every phase has >= 1 testcase; every testcase maps to a task.\n\n"
            "## Reference files\n\n"
            "- `references/house-style.md`\n- `references/main-repo.md`\n"
            "- `references/solution-repo.md`\n- `references/validation-repo.md`\n"
            "- `references/testcase-and-marks.md`\n- `scripts/check_consistency.py`\n"
        )
    if key == "house_style":
        return (
            f"# House style ({template.domain.upper()} {ct})\n\n"
            f"Derived from {len(template.derived_from)} real assessment(s).\n\n"
            f"## Norms\n\n"
            f"- Phases: typically {(hs.get('phase_count') or {}).get('median')} "
            f"(range {(hs.get('phase_count') or {}).get('min')}-{(hs.get('phase_count') or {}).get('max')}).\n"
            f"- Testcases: typically {(hs.get('testcase_count') or {}).get('median')}.\n"
            f"- Total marks: default **{total}** (observed {(hs.get('total_marks') or {}).get('values')}).\n"
            f"- Duration (min): default {(hs.get('duration_minutes') or {}).get('default')}.\n"
            f"- Grader format: `{grader}`.\n\n"
            f"## Common AWS services\n\n{_bullet(hs.get('top_services', []))}\n\n"
            f"## Testcase categories\n\n{_bullet(hs.get('testcase_categories', []))}\n\n"
            f"## Required _Main files\n\n{_bullet(st.get('required_main_files', []))}\n\n"
            f"## Resource-naming discipline\n\n- {hs.get('exact_name_discipline','')}\n"
            f"- Common prefixes: {(hs.get('resource_naming') or {}).get('common_prefixes')}\n"
            f"- Examples: {(hs.get('resource_naming') or {}).get('examples')}\n"
        )
    if key == "main_repo":
        files = _bullet(st.get("required_main_files", []))
        return (
            "# Building the _Main repo (learner-facing)\n\n"
            "This is the ONLY repo the learner sees. It contains the task and a starter project.\n\n"
            f"## File layout\n\n{files}\n\n"
            "## Task document skeleton (`Assessment-Activities.md`)\n\n"
            "```markdown\n"
            "# <Title> Assessment\n\n"
            "### Duration + Lab Preparation Time\n- **Total:** <N> minutes\n\n"
            "## What You Will Be Provided\n- ...\n\n## What You Need to Know\n- ...\n\n"
            "## Scenario\n<realistic business situation>\n\n"
            "# Phase 1 - <Name>\n## Objective\n<...>\n## Tasks\n"
            "1. Create <resource> named **exact-name**.\n\n"
            "# Testcases\n## Phase 1 - <Name>\n- Validate <...>. **(Marks = N)**\n"
            "```\n\n"
            "## Rules\n\n"
            "- State EXACT resource names in **bold**; the grader checks these verbatim.\n"
            "- Do NOT include solution code, commands that solve the task, or answer keys.\n"
            f"- Marks in the Testcases section MUST sum to {total}.\n"
        )
    if key == "solution_repo":
        return (
            "# Building the _Solution repo (evaluator-only)\n\n"
            "Mirror the `_Main` starter project with every `// TODO` / gap completed so the project "
            "passes all testcases. This repo is NEVER shown to the learner.\n\n"
            "## Rules\n\n"
            "- Same file/package structure as the `_Main` starter project.\n"
            "- Implement all required endpoints/resources/logic to satisfy the grader.\n"
            "- Keep any secret/expected values here (and in `_Validation`), never in `_Main`.\n"
            f"- Tech stack anchor: {json.dumps((ex or {}).get('grader_format', grader))}\n"
        )
    if key == "validation_repo":
        py = (
            "## Python harness layout\n\n"
            "- `validate.py` (entry), `test_cases.py` (checks), `result_output.py`, "
            "`report_handler.py`, `logger_setup.py`, `testcase_output.py`, `resultTemplate.json`.\n\n"
            "## test_cases.py contract\n\n"
            "```python\n"
            "TESTCASE_MARKS = {\n    \"testcase1_...\": 8,\n    \"testcase2_...\": 6,\n    # sum == "
            f"{total}\n" "}\n\n"
            "# group checks into milestones matching the task-doc phases:\n"
            "self.add_milestone(\"Phase 1 - <Name>\", [\"testcase1_...\", \"testcase2_...\"])\n"
            "```\n\nOne `testcaseN_*` method per task bullet; each awards its marks on pass, 0 on fail.\n"
        )
        js = (
            "## JSON testcases layout\n\n"
            "- `metadata.json` (deliverables, technical_requirements, business_rules, tech_stack).\n"
            "- `test_cases.json`: a list of objects "
            "`{id,name,category,marks,endpoint,httpMethod,expectedStatusCode,expectedResponse,...}`.\n"
        )
        chosen = py if grader == "python_harness" else js
        return (
            "# Building the _Validation grader (evaluator-only)\n\n"
            f"Recommended format for this family: `{grader}`.\n\n"
            f"{chosen}\n"
            "## Rules\n\n- One check per task bullet.\n"
            f"- Marks per check; the total MUST be {total}.\n"
            "- Check the EXACT resource names stated in the task doc.\n"
            "- Emit a result JSON (schema 2.0: metadata/context/summary/testCases).\n"
        )
    if key == "testcase_marks":
        return (
            "# Testcase schema & consistency contract\n\n"
            "## Testcase object\n\n```json\n"
            + json.dumps(ts.get("fields", {}), indent=2)
            + "\n```\n\n## Rules\n\n"
            f"- {ts.get('marks_rule','sum(testcase.marks) == total_marks')} (total = {total}).\n"
            f"- {ts.get('grouping','group testcases into phases matching the task doc')}.\n\n"
            "## Consistency contract (must all hold)\n\n"
            "1. Every phase in the task doc has >= 1 testcase.\n"
            "2. Every testcase maps to a task bullet.\n"
            f"3. sum(marks) == {total}.\n"
            "4. Every exact resource name checked appears verbatim in the task doc.\n"
            "5. No solution/answer-key/expected-value in `_Main`.\n"
            "6. `_Solution` passes every testcase.\n"
        )
    return ""


def compile_skill(template: Template, *, example: AssessmentRecord | None = None) -> SkillFile:
    """Deterministic (offline) multi-file package. No model required."""
    name = f"aws-{template.content_type.replace('_', '-')}-author"
    fm = _front_matter(template, name)
    files: dict[str, str] = {}
    for rel, key, _ in FILE_PLAN:
        files[rel] = _det_file(key, template, example, fm)
    files["scripts/check_consistency.py"] = CHECK_SCRIPT
    skill = SkillFile(
        skill_id=stable_id("skl", {"template": template.template_id, "name": name,
                                    "mode": "deterministic", "time": utc_now()}),
        name=name, template_id=template.template_id, domain=template.domain,
        content_type=template.content_type, status="ready", entry="SKILL.md",
        files=files, model_ref={"mode": "deterministic"},
    )
    return skill.finalize()


# ---- model package -------------------------------------------------------

_STYLE = """Nuvepro TLS skill house style (match it exactly):
- Start every .md with YAML front-matter: name and description only.
- Then a short title line.
- Use concise, structured sections with emoji headers, e.g.:
  ## 🎯 Purpose
  ## 🧠 Core Principles
  ## 🔥 Difficulty Standard
  ## ⚠️ Strict Rules   (a "Do NOT" list)
  ## 📌 Output Expectations
  ## 🧠 Quality Check   (a "before finalizing" checklist)
- Be concise and practical. Bullet points over paragraphs. No filler.
- Prefer hands-on, real-world, scenario-based design over theory/MCQ.
- Senior-engineer tone; ready-to-use; reduce back-and-forth."""

_SYSTEM = """You are a principal instructional-design engineer at Nuvepro (TLS team).

Produce a STRUCTURED SKILL PACKAGE (several small Markdown files) that an AI
coding agent will read to generate a COMPLETE Nuvepro cloud assessment as three
repositories:
  <base>_Main        learner-facing task + starter project (only thing the learner sees)
  <base>_Solution    evaluator-only reference answer that passes every check
  <base>_Validation  evaluator-only automated grader that scores a live cloud account

Non-negotiable rules the package must enforce on its user:
- The task document states EXACT resource names; the grader checks the same names byte-for-byte.
- sum(testcase marks) == the declared total.
- Never put solution code, answer keys, or grader expected-values into _Main.
- Every phase has >= 1 testcase; every testcase maps to a task.
- Real-world, hands-on, debugging/decision-making difficulty (not trivial, not MCQ-only).

{style}

OUTPUT FORMAT (critical): return ALL files in ONE response using this exact
delimiter format and NOTHING else (no preamble, no code fences):

===FILE: SKILL.md===
<content>
===FILE: references/main-repo.md===
<content>
===FILE: references/solution-repo.md===
<content>
===FILE: references/validation-repo.md===
<content>
===FILE: references/testcase-and-marks.md===
<content>
===END===

SKILL.md is the router the agent reads first; it must summarize the workflow,
the three repos, the hard rules, and point to the reference files.""".replace("{style}", _STYLE)


_FILE_RE = None


def _parse_multifile(text: str) -> dict[str, str]:
    import re
    files: dict[str, str] = {}
    # split on ===FILE: path===
    parts = re.split(r"(?m)^===FILE:\s*(.+?)\s*===\s*$", text)
    # parts = [pre, path1, body1, path2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        path = parts[i].strip()
        body = parts[i + 1]
        body = re.split(r"(?m)^===END===\s*$", body)[0]
        files[path] = body.strip() + "\n"
    return files


_FILE_SYSTEM = """You are a principal instructional-design engineer at Nuvepro (TLS team).

You are writing ONE file of a multi-file SKILL PACKAGE. An AI agent later reads
the whole package to generate a COMPLETE Nuvepro cloud assessment as three repos:
  <base>_Main (learner-facing), <base>_Solution (evaluator-only reference),
  <base>_Validation (evaluator-only grader).

Non-negotiable rules the package enforces:
- Task doc states EXACT resource names; grader checks the same names byte-for-byte.
- sum(testcase marks) == the declared total.
- Never put solution code, answer keys, or grader expected-values into _Main.
- Every phase has >= 1 testcase; every testcase maps to a task.
- Real-world hands-on difficulty (debugging/decision-making), not trivial MCQ.

{style}

Output ONLY the Markdown content of the requested file. No preamble, no
commentary, no surrounding code fence.""".replace("{style}", _STYLE)


def compile_skill_with_model(
    template: Template,
    *,
    example: AssessmentRecord | None,
    settings: ModelSettings,
) -> SkillFile:
    """Author the multi-file package with one focused LLM call per file.

    Per-file calls guarantee each file completes (no mid-file truncation) and keep
    each request small and fast.
    """
    import dataclasses

    name = f"aws-{template.content_type.replace('_', '-')}-author"
    fm = _front_matter(template, name)
    ctx = json.dumps(_context(template, example), ensure_ascii=False, indent=2)
    per_file = dataclasses.replace(settings, max_tokens=min(settings.max_tokens, 4500))

    files: dict[str, str] = {}
    usage_total: dict[str, int] = {}
    for rel, key, focus in FILE_PLAN:
        fm_hint = ""
        if key == "router":
            fm_hint = ("Begin the file with this EXACT YAML front-matter, then the body:\n"
                       + _fm_block(fm) + "\n")
        user = (
            f"Write the file `{rel}` of the skill package for authoring AWS "
            f"{template.content_type.replace('_',' ')}s.\n\n"
            f"Purpose of THIS file: {focus}\n\n{fm_hint}"
            f"Ground everything in this approved template + worked example:\n{ctx}\n"
        )
        text, ref = generate_text(per_file, system=_FILE_SYSTEM, user=user)
        files[rel] = strip_code_fence(text)
        for k, v in (ref.get("usage") or {}).items():
            if isinstance(v, int):
                usage_total[k] = usage_total.get(k, 0) + v
    files["scripts/check_consistency.py"] = CHECK_SCRIPT
    skill = SkillFile(
        skill_id=stable_id("skl", {"template": template.template_id, "name": name,
                                    "model": settings.model, "time": utc_now()}),
        name=name, template_id=template.template_id, domain=template.domain,
        content_type=template.content_type, status="ready", entry="SKILL.md",
        files=files,
        model_ref={"mode": "model", "model": settings.model, "usage": usage_total},
    )
    return skill.finalize()
