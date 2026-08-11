"""Regenerate EXPERIMENTS_REPORT.html from run artifacts (compact).

Usage:
  uv run python -m skill_lab.export_experiments_html
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from openrouter import load_dotenv
from skill_lab.metrics import compute_automatic_metrics
from skill_lab.models import Assessment

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "data" / "skill_lab"
RUN_ID = "run_be199f1c4ed5e951"
OUT = LAB / "EXPERIMENTS_REPORT.html"


def _ensure_auto(run: Path) -> dict:
    report_path = run / "05-comparison" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    auto = report.get("automatic_metrics")
    if auto and auto.get("bleu", {}).get("corpus") is not None:
        return auto
    load_dotenv()
    gen = [Assessment.from_dict(x) for x in json.loads((run / "04-generated" / "index.json").read_text(encoding="utf-8"))]
    hold = [Assessment.from_dict(x) for x in json.loads((run / "02-split.json").read_text(encoding="utf-8"))["holdout"]]
    auto = compute_automatic_metrics(gen, hold, report.get("pairs"))
    report["automatic_metrics"] = auto
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (run / "05-comparison" / "automatic_metrics.json").write_text(json.dumps(auto, indent=2), encoding="utf-8")
    return auto


def main() -> None:
    run = LAB / "runs" / RUN_ID
    e2e = json.loads((LAB / "e2e_report.json").read_text(encoding="utf-8"))
    report = json.loads((run / "05-comparison" / "report.json").read_text(encoding="utf-8"))
    auto = _ensure_auto(run)
    assessments = json.loads((run / "01-assessments.json").read_text(encoding="utf-8"))
    dims = report.get("dimensions") or {}
    pairs = report.get("pairs") or []
    bleu = auto["bleu"]
    emb = auto["embedding"]

    # Keep regenerator tiny: refresh the polished static report's auto-metrics note file,
    # and leave EXPERIMENTS_REPORT.html as the curated one-shot (edit that file for prose).
    # This script verifies numbers and writes a machine sidecar for CI/diffs.
    sidecar = {
        "date": str(date.today()),
        "run_id": RUN_ID,
        "verdict": e2e.get("verdict") or e2e.get("summary"),
        "sme_overall": report.get("overall_score"),
        "dimensions": {k: (v or {}).get("score") for k, v in dims.items()},
        "pairs": [{"generated_id": p.get("generated_id"), "holdout_id": p.get("holdout_id"), "score": p.get("score")} for p in pairs],
        "automatic_metrics": auto,
        "assessment_count": len(assessments),
        "html": str(OUT.relative_to(ROOT)).replace("\\", "/"),
        "note": "Polished HTML is curated at EXPERIMENTS_REPORT.html; this JSON is the regenerable numeric snapshot.",
    }
    snap = LAB / "experiments_snapshot.json"
    snap.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(f"snapshot={snap}")
    print(f"html={OUT} (curated; open in browser)")
    print(
        f"SME={report.get('overall_score')} "
        f"BLEU={bleu.get('corpus')} "
        f"embed={emb.get('mean_cosine')} "
        f"pairing={auto.get('pairing')}"
    )


if __name__ == "__main__":
    main()
