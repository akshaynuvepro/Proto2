"""Read-only browsing of past runs from disk (for the UI run history)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import ROOT

# manifest step keys in pipeline order, with display labels
STAGES: list[tuple[str, str]] = [
    ("ingest_split", "split"),
    ("03-skill", "skill"),
    ("generate", "generate"),
    ("compare", "baseline compare"),
    ("improve", "improve"),
    ("verify", "verify"),
]


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def list_all_runs() -> list[dict[str, Any]]:
    """Every run on disk (newest first) with progress, status and scores."""
    out: list[dict[str, Any]] = []
    if not ROOT.exists():
        return out
    for d in sorted(ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        m = _read_json(d / "manifest.json") or {}
        steps = m.get("steps") or {}
        done = [label for key, label in STAGES if key in steps]
        if "verify" in steps:
            status = "completed"
        elif not done:
            status = "empty"
        else:
            idx = max(i for i, (k, _) in enumerate(STAGES) if k in steps)
            nxt = STAGES[idx + 1][1] if idx + 1 < len(STAGES) else "?"
            status = f"stopped before {nxt}"
        verify = steps.get("verify") or {}
        compare = steps.get("compare") or {}
        out.append(
            {
                "run_id": d.name,
                "created_at": m.get("created_at"),
                "skill_generation": int(m.get("skill_generation") or 1),
                "resumed_from": m.get("resumed_from"),
                "resumable": (d / "07-improved-skill" / "package.json").exists()
                and (d / "02-split.json").exists(),
                "stages_done": done,
                "status": status,
                "baseline": verify.get("baseline_overall", compare.get("overall_score")),
                "improved": verify.get("improved_overall"),
                "delta": verify.get("delta_overall"),
                "verdict": verify.get("verdict"),
            }
        )
    return out


def _report_line(report: dict[str, Any]) -> str:
    dims = report.get("dimensions") or {}
    dim_line = " · ".join(f"{k} **{(v or {}).get('score', '—')}**" for k, v in dims.items())
    return f"**SME rubric score: {report.get('overall_score')} / 10**\n\n{dim_line}"


def _skill_docs(prefix: str, files: dict[str, str]) -> list[tuple[str, str]]:
    order = ["SKILL.md"] + sorted(k for k in files if k != "SKILL.md")
    return [(f"{prefix} · {k}", files[k]) for k in order if k in files]


def report_markdown(report: dict[str, Any], title: str = "Comparison report") -> str:
    """Render a comparison report as a clean human-readable document."""
    lines = [f"# {title}", "", f"**Overall SME score: {report.get('overall_score')} / 10**"]

    dims = report.get("dimensions") or {}
    if dims:
        lines += ["", "## Dimension scores", "", "| Dimension | Score | Notes |", "|---|---|---|"]
        for k, v in dims.items():
            v = v or {}
            notes = str(v.get("notes") or "").replace("|", "\\|")
            lines.append(f"| {k} | {v.get('score', '—')} | {notes} |")

    pairs = report.get("pairs") or []
    if pairs:
        lines += ["", "## Pair analysis (generated ↔ holdout)"]
        for p in pairs:
            lines += [
                "",
                f"### {p.get('generated_id')} ↔ {p.get('holdout_id')} — score {p.get('score')}",
            ]
            if p.get("strengths"):
                lines += ["", "**Strengths**", ""] + [f"- {s}" for s in p["strengths"]]
            if p.get("gaps"):
                lines += ["", "**Gaps**", ""] + [f"- {g}" for g in p["gaps"]]

    fixes = report.get("priority_fixes") or []
    if fixes:
        lines += ["", "## Priority fixes", ""]
        for f in fixes:
            lines.append(f"- **P{f.get('priority', '?')} — {f.get('issue', '')}**")
            if f.get("recommendation"):
                lines.append(f"  - Fix: {f['recommendation']}")

    if report.get("improvement_brief"):
        lines += ["", "## Improvement brief", "", str(report["improvement_brief"])]

    auto = report.get("automatic_metrics") or {}
    if auto:
        bleu = (auto.get("bleu") or {}).get("corpus")
        emb = (auto.get("embedding") or {}).get("mean_cosine")
        lines += [
            "",
            "## Topic-drift indicators (not quality)",
            "",
            f"- BLEU corpus: {bleu}",
            f"- Embedding mean cosine: {emb}",
        ]

    if report.get("summary_markdown"):
        lines += ["", "## SME summary", "", str(report["summary_markdown"])]
    return "\n".join(lines)


def _verdict_markdown(verdict: dict[str, Any]) -> str:
    lines = [
        "# Verdict",
        "",
        f"**{verdict.get('verdict', '—')}** · Δ overall: **{verdict.get('delta_overall', '—')}** "
        f"(noise threshold ±{verdict.get('noise_threshold', 0.3)})",
        "",
        "| Dimension | Before | After | Δ |",
        "|---|---|---|---|",
    ]
    for k, v in (verdict.get("dimensions") or {}).items():
        v = v or {}
        lines.append(
            f"| {k} | {v.get('baseline', '—')} | {v.get('improved', '—')} | {v.get('delta', '—')} |"
        )
    lines.append(
        f"| **overall** | **{verdict.get('baseline_overall', '—')}** | "
        f"**{verdict.get('improved_overall', '—')}** | **{verdict.get('delta_overall', '—')}** |"
    )
    return "\n".join(lines)


def stage_status(run_id: str) -> list[dict[str, Any]]:
    """The same 8 stages shown while a pipeline runs, with done/not-done status."""
    base = ROOT / run_id
    m = _read_json(base / "manifest.json") or {}
    steps = m.get("steps") or {}
    gen_num = int(m.get("skill_generation") or 1)
    resumed = bool(m.get("resumed_from"))
    return [
        {
            "label": "Load prior run" if resumed else "Split 10 train / 10 holdout",
            "done": "ingest_split" in steps,
        },
        {
            "label": f"Load improved skill v{gen_num}" if resumed else "Create skill v1",
            "done": "03-skill" in steps,
        },
        {"label": "Generate 10 (current skill)", "done": "generate" in steps},
        {"label": "SME compare — baseline score", "done": "compare" in steps},
        {"label": f"Improver → improved skill v{gen_num + 1}", "done": "improve" in steps},
        {
            "label": "Re-generate 10 (improved skill)",
            "done": (base / "08-improved-generated" / "index.json").exists(),
        },
        {
            "label": "SME re-compare — improved score",
            "done": (base / "09-improved-comparison" / "report.json").exists(),
        },
        {"label": "Δ verdict", "done": (base / "10-verdict.json").exists()},
    ]


def stage_status_markdown(run_id: str) -> str:
    """Minimal side-panel view: stages + status only (like the live task tracker)."""
    lines = []
    stopped_marked = False
    for s in stage_status(run_id):
        if s["done"]:
            lines.append(f"✅ {s['label']}")
        elif not stopped_marked:
            lines.append(f"⚠️ {s['label']} — stopped here")
            stopped_marked = True
        else:
            lines.append(f"▫️ {s['label']}")
    return "## Stages\n\n" + "\n\n".join(lines)


def run_dossier(run_id: str) -> str:
    """One-page overview of a run (opened by clicking its id in the runs table)."""
    bundle = load_run_bundle(run_id)
    m = bundle["manifest"]
    gen = bundle["skill_generation"]
    steps = m.get("steps") or {}

    lines = [f"# Run {run_id}", ""]
    lines.append(f"- **Created:** {str(m.get('created_at') or '—')[:19]}")
    lines.append(f"- **Skill generation:** v{gen}")
    if m.get("resumed_from"):
        lines.append(f"- **Resumed from:** {m['resumed_from']}")

    lines += ["", "## Stages", ""]
    for key, label in STAGES:
        mark = "✅" if key in steps else "▫️"
        lines.append(f"- {mark} {label}")

    compare = steps.get("compare") or {}
    verify = steps.get("verify") or {}
    if compare or verify:
        lines += ["", "## Scores", ""]
        if compare.get("overall_score") is not None:
            lines.append(f"- Baseline (v{gen}): **{compare.get('overall_score')}**")
        if verify.get("improved_overall") is not None:
            lines.append(f"- Improved (v{gen + 1}): **{verify.get('improved_overall')}**")
            lines.append(f"- Δ: **{verify.get('delta_overall')}** → {verify.get('verdict')}")

    verdict = bundle.get("verdict")
    if verdict:
        lines += ["", _verdict_markdown(verdict)]

    lines += ["", "## Documents by stage", ""]
    for s in bundle["sections"]:
        docs = s.get("docs") or []
        lines.append(f"**{s['title']}**")
        lines += [f"- {n}" for n, _ in docs] or ["- (no documents)"]
        lines.append("")

    lines += [
        "---",
        f"➡ Read every document: send `open {run_id}`",
        f"➡ Continue optimizing: send `resume {run_id}`",
    ]
    return "\n".join(lines)


def load_run_bundle(run_id: str) -> dict[str, Any]:
    """Stage-wise sections of a run: title, summary, readable documents."""
    base = ROOT / run_id
    if not base.is_dir():
        raise FileNotFoundError(f"run not found: {run_id}")
    m = _read_json(base / "manifest.json") or {}
    gen_num = int(m.get("skill_generation") or 1)
    sections: list[dict[str, Any]] = []

    split = _read_json(base / "02-split.json")
    if split:
        train = ", ".join(a["id"] for a in split.get("train") or [])
        hold = ", ".join(a["id"] for a in split.get("holdout") or [])
        sections.append(
            {
                "title": "1️⃣ Split",
                "summary": f"seed `{split.get('seed')}`\n\n**Train:** {train}\n\n**Holdout:** {hold}",
                "docs": [],
            }
        )

    pkg = _read_json(base / "03-skill" / "package.json")
    if pkg:
        sections.append(
            {
                "title": f"2️⃣ Skill v{gen_num}",
                "summary": str(pkg.get("summary") or ""),
                "docs": _skill_docs(f"skill v{gen_num}", pkg.get("files") or {}),
            }
        )

    gen = _read_json(base / "04-generated" / "index.json")
    if gen:
        sections.append(
            {
                "title": f"3️⃣ Generated with skill v{gen_num}",
                "summary": f"{len(gen)} assessments",
                "docs": [(f"{a['id']} · {a['title'][:60]}", a["body"]) for a in gen],
            }
        )

    rep = _read_json(base / "05-comparison" / "report.json")
    if rep:
        sections.append(
            {
                "title": "4️⃣ Baseline compare",
                "summary": _report_line(rep),
                "docs": [
                    (
                        f"Baseline report — skill v{gen_num}",
                        report_markdown(rep, f"Baseline report — skill v{gen_num}"),
                    ),
                ],
            }
        )

    improver = _read_text(base / "06-improver" / "IMPROVER_SKILL.md")
    ipkg = _read_json(base / "07-improved-skill" / "package.json")
    if improver or ipkg:
        docs: list[tuple[str, str]] = []
        if improver:
            docs.append((f"IMPROVER_SKILL.md (v{gen_num}→v{gen_num + 1})", improver))
        if ipkg:
            docs += _skill_docs(f"skill v{gen_num + 1}", ipkg.get("files") or {})
        sections.append(
            {
                "title": f"5️⃣ Improved skill v{gen_num + 1}",
                "summary": str((ipkg or {}).get("summary") or ""),
                "docs": docs,
            }
        )

    regen = _read_json(base / "08-improved-generated" / "index.json")
    if regen:
        sections.append(
            {
                "title": f"6️⃣ Re-generated with skill v{gen_num + 1}",
                "summary": f"{len(regen)} assessments",
                "docs": [(f"{a['id']} · {a['title'][:60]}", a["body"]) for a in regen],
            }
        )

    rep2 = _read_json(base / "09-improved-comparison" / "report.json")
    if rep2:
        sections.append(
            {
                "title": "7️⃣ Improved compare",
                "summary": _report_line(rep2),
                "docs": [
                    (
                        f"Improved report — skill v{gen_num + 1}",
                        report_markdown(rep2, f"Improved report — skill v{gen_num + 1}"),
                    ),
                ],
            }
        )

    verdict_data = _read_json(base / "10-verdict.json")
    if verdict_data:
        sections.append(
            {
                "title": "8️⃣ Verdict",
                "summary": f"verdict: **{verdict_data.get('verdict', '—')}** · "
                f"Δ overall: **{verdict_data.get('delta_overall', '—')}**",
                "docs": [("Verdict — scores & deltas", _verdict_markdown(verdict_data))],
            }
        )

    return {
        "run_id": run_id,
        "manifest": m,
        "skill_generation": gen_num,
        "sections": sections,
        "verdict": _read_json(base / "10-verdict.json"),
    }
