#!/usr/bin/env python3
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
    m = re.search(r"Total\s+Marks?\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    if m:
        doc_total = float(m.group(1))
    if doc_total is not None and abs(doc_total - total_marks) > 0.001:
        problems.append(f"marks mismatch: testcases sum {total_marks} != doc total {doc_total}")

    doc_phases = set(re.findall(r"(?im)^#\s*(Phase\s+\d+)", text))
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
