"""Orchestrate the full skill-lab pipeline (closed loop).

Loop shape:
  ingest -> split -> skill (v N) -> generate -> compare (baseline score)
        -> improver -> improved skill (v N+1)
        -> RE-generate with improved skill -> RE-compare vs SAME holdout
        -> delta verdict (did the skill actually get better?)

Cross-run: a new run can adopt a prior run's improved skill + split
(`adopt_prior_run`), so run N+1 continues optimizing v N+1 instead of
rebuilding a seed skill from scratch.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from openrouter import OpenRouterSettings, load_dotenv

from .compare import compare_agent
from .create_skill import create_skill
from .generate import generate_assessments
from .improve import apply_improvement, create_improvement_skill
from .ingest import require_twenty
from .models import Assessment, SkillPackage, Split
from .split import split_train_holdout
from .store import ROOT as RUNS_ROOT
from .store import RunStore, run_dir

# LLM-judge repeat variance: deltas inside this band are "no provable change".
NOISE_THRESHOLD = 0.3

ProgressCb = Callable[[int, int, str], None]


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_delta(baseline_report: dict[str, Any], improved_report: dict[str, Any]) -> dict[str, Any]:
    """before/after scores + per-dimension deltas + noise-aware verdict."""
    base = _to_float(baseline_report.get("overall_score"))
    improved = _to_float(improved_report.get("overall_score"))
    overall = round(improved - base, 2) if base is not None and improved is not None else None
    if overall is None:
        verdict = "unknown"
    elif overall > NOISE_THRESHOLD:
        verdict = "improved"
    elif overall < -NOISE_THRESHOLD:
        verdict = "regressed"
    else:
        verdict = "within_noise"

    dims: dict[str, dict[str, float | None]] = {}
    base_dims = baseline_report.get("dimensions") or {}
    imp_dims = improved_report.get("dimensions") or {}
    for key in sorted(set(base_dims) | set(imp_dims)):
        b = _to_float((base_dims.get(key) or {}).get("score"))
        i = _to_float((imp_dims.get(key) or {}).get("score"))
        dims[key] = {
            "baseline": b,
            "improved": i,
            "delta": round(i - b, 2) if b is not None and i is not None else None,
        }
    return {
        "baseline_overall": base,
        "improved_overall": improved,
        "delta_overall": overall,
        "noise_threshold": NOISE_THRESHOLD,
        "verdict": verdict,
        "dimensions": dims,
    }


def list_resumable_runs() -> list[dict[str, Any]]:
    """Runs that saved an improved skill + split (newest first)."""
    out: list[dict[str, Any]] = []
    if not RUNS_ROOT.exists():
        return out
    for d in sorted(RUNS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        pkg = d / "07-improved-skill" / "package.json"
        split = d / "02-split.json"
        if not (pkg.exists() and split.exists()):
            continue
        generation = 1
        verdict: dict[str, Any] = {}
        try:
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            generation = int(m.get("skill_generation") or 1)
            verdict = (m.get("steps") or {}).get("verify") or {}
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        out.append(
            {
                "run_id": d.name,
                "skill_generation": generation,
                "improved_generation": generation + 1,
                "verify": {
                    k: verdict.get(k)
                    for k in ("baseline_overall", "improved_overall", "delta_overall", "verdict")
                },
            }
        )
    return out


def load_prior_run(run_id: str) -> tuple[list[Assessment], Split, SkillPackage, int]:
    """Load assessments, split, improved skill and next generation number from a prior run."""
    base = run_dir(run_id)
    split_path = base / "02-split.json"
    pkg_path = base / "07-improved-skill" / "package.json"
    if not split_path.exists():
        raise FileNotFoundError(f"{run_id}: missing 02-split.json (cannot resume)")
    if not pkg_path.exists():
        raise FileNotFoundError(f"{run_id}: missing 07-improved-skill/package.json (cannot resume)")

    split_data = json.loads(split_path.read_text(encoding="utf-8"))
    train = [Assessment.from_dict(a) for a in split_data["train"]]
    holdout = [Assessment.from_dict(a) for a in split_data["holdout"]]
    split = Split(train=train, holdout=holdout, seed=int(split_data["seed"]))

    skill = SkillPackage.from_dict(json.loads(pkg_path.read_text(encoding="utf-8")))
    generation = 1
    try:
        m = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        generation = int(m.get("skill_generation") or 1)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return [*train, *holdout], split, skill, generation + 1


class Pipeline:
    def __init__(self, store: RunStore | None = None, settings: OpenRouterSettings | None = None) -> None:
        load_dotenv()
        self.store = store or RunStore()
        self.settings = settings or OpenRouterSettings.from_env()
        self.assessments: list[Assessment] = []
        self.split: Split | None = None
        self.skill: SkillPackage | None = None
        self.skill_generation: int = 1
        self.resumed_from: str | None = None
        self.generated: list[Assessment] = []
        self.report: dict[str, Any] | None = None
        self.improver_md: str = ""
        self.improved: SkillPackage | None = None
        self.regenerated: list[Assessment] = []
        self.improved_report: dict[str, Any] | None = None
        self.delta: dict[str, Any] | None = None

    # ---------- fresh start ----------

    def set_assessments(self, items: list[Assessment], *, seed: int | None = None) -> Split:
        self.assessments = require_twenty(items)
        self.store.save_assessments(self.assessments)
        self.split = split_train_holdout(self.assessments, seed=seed)
        self.store.save_split(self.split)
        self.store.mark_step("ingest_split", {"count": 20, "seed": self.split.seed})
        return self.split

    # ---------- cross-run continuation ----------

    def adopt_prior_run(self, run_id: str) -> tuple[Split, SkillPackage]:
        """Continue optimizing a prior run's improved skill on the SAME split."""
        items, split, skill, generation = load_prior_run(run_id)
        self.assessments = items
        self.split = split
        self.skill = skill
        self.skill_generation = generation
        self.resumed_from = run_id
        self.store.save_assessments(items)
        self.store.save_split(split)
        self.store.save_skill(skill, "03-skill")
        self.store.set_meta("skill_generation", generation)
        self.store.set_meta("resumed_from", run_id)
        self.store.mark_step(
            "ingest_split",
            {"count": len(items), "seed": split.seed, "resumed_from": run_id},
        )
        return split, skill

    # ---------- loop stages ----------

    def build_skill(self) -> SkillPackage:
        assert self.split is not None
        if self.skill is not None and self.resumed_from:
            # Adopted from a prior run — do not rebuild from scratch.
            return self.skill
        self.skill, _ = create_skill(self.split.train, settings=self.settings)
        self.store.save_skill(self.skill, "03-skill")
        self.store.set_meta("skill_generation", self.skill_generation)
        return self.skill

    def generate(
        self,
        topics: list[str] | None = None,
        *,
        progress_cb: ProgressCb | None = None,
    ) -> list[Assessment]:
        assert self.skill is not None and self.split is not None
        self.generated, _ = generate_assessments(
            self.skill,
            topics=topics,
            train=self.split.train,
            count=10,
            settings=self.settings,
            id_prefix="gen",
            progress_cb=progress_cb,
        )
        self.store.save_generated(self.generated)
        self.store.mark_step("generate", {"count": len(self.generated)})
        return self.generated

    def compare(self) -> dict[str, Any]:
        assert self.split is not None and self.generated
        self.report, meta = compare_agent(self.generated, self.split.holdout, settings=self.settings)
        self.store.save_comparison(self.report)
        auto = self.report.get("automatic_metrics") or {}
        bleu = (auto.get("bleu") or {}).get("corpus")
        emb = (auto.get("embedding") or {}).get("mean_cosine")
        self.store.mark_step(
            "compare",
            {
                "overall_score": self.report.get("overall_score"),
                "bleu_corpus": bleu,
                "embedding_mean_cosine": emb,
                "tools_used": meta.get("tools_used"),
                "agent_rounds": meta.get("agent_rounds"),
            },
        )
        return self.report

    def improve(self) -> tuple[str, SkillPackage]:
        assert self.skill is not None and self.report is not None
        holdout = self.split.holdout if self.split else []
        self.improver_md, improver_meta = create_improvement_skill(
            self.report,
            self.skill,
            generated=self.generated,
            holdout=holdout,
            settings=self.settings,
        )
        self.store.save_improver(self.improver_md)
        self.improved, apply_meta = apply_improvement(
            self.skill,
            self.improver_md,
            self.report,
            generated=self.generated,
            holdout=holdout,
            settings=self.settings,
        )
        self.store.save_skill(self.improved, "07-improved-skill")
        self.store.mark_step(
            "improve",
            {
                "summary": self.improved.summary,
                "improver_tools": improver_meta.get("tools_used"),
                "apply_tools": apply_meta.get("tools_used"),
            },
        )
        return self.improver_md, self.improved

    # ---------- closed-loop verification ----------

    def verify(
        self,
        *,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[Assessment], dict[str, Any], dict[str, Any]]:
        """Re-generate with the improved skill, re-compare vs the SAME holdout,
        and compute the before/after delta.

        Controls: same topics (train titles), same holdout, same judge —
        the improved skill is the only changed variable.
        """
        assert self.improved is not None, "run improve() first"
        assert self.split is not None and self.report is not None

        self.regenerated, _ = generate_assessments(
            self.improved,
            topics=None,  # same source: train titles
            train=self.split.train,
            count=10,
            settings=self.settings,
            id_prefix="gen2",
            progress_cb=progress_cb,
        )
        self.store.save_generated(self.regenerated, folder="08-improved-generated")

        self.improved_report, meta = compare_agent(
            self.regenerated, self.split.holdout, settings=self.settings
        )
        self.store.save_comparison(self.improved_report, folder="09-improved-comparison")

        self.delta = compute_delta(self.report, self.improved_report)
        self.store.write_json("10-verdict.json", self.delta)
        self.store.mark_step(
            "verify",
            {
                "baseline_overall": self.delta["baseline_overall"],
                "improved_overall": self.delta["improved_overall"],
                "delta_overall": self.delta["delta_overall"],
                "verdict": self.delta["verdict"],
                "tools_used": meta.get("tools_used"),
                "agent_rounds": meta.get("agent_rounds"),
            },
        )
        return self.regenerated, self.improved_report, self.delta
