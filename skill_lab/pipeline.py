"""Orchestrate the full skill-lab pipeline."""

from __future__ import annotations

from typing import Any

from openrouter import OpenRouterSettings, load_dotenv

from .compare import compare_agent
from .create_skill import create_skill
from .generate import generate_assessments
from .improve import apply_improvement, create_improvement_skill
from .ingest import require_twenty
from .models import Assessment, SkillPackage, Split
from .split import split_train_holdout
from .store import RunStore


class Pipeline:
    def __init__(self, store: RunStore | None = None, settings: OpenRouterSettings | None = None) -> None:
        load_dotenv()
        self.store = store or RunStore()
        self.settings = settings or OpenRouterSettings.from_env()
        self.assessments: list[Assessment] = []
        self.split: Split | None = None
        self.skill: SkillPackage | None = None
        self.generated: list[Assessment] = []
        self.report: dict[str, Any] | None = None
        self.improver_md: str = ""
        self.improved: SkillPackage | None = None

    def set_assessments(self, items: list[Assessment], *, seed: int | None = None) -> Split:
        self.assessments = require_twenty(items)
        self.store.save_assessments(self.assessments)
        self.split = split_train_holdout(self.assessments, seed=seed)
        self.store.save_split(self.split)
        self.store.mark_step("ingest_split", {"count": 20, "seed": self.split.seed})
        return self.split

    def build_skill(self) -> SkillPackage:
        assert self.split is not None
        self.skill, _ = create_skill(self.split.train, settings=self.settings)
        self.store.save_skill(self.skill, "03-skill")
        return self.skill

    def generate(self, topics: list[str] | None = None) -> list[Assessment]:
        assert self.skill is not None and self.split is not None
        self.generated, _ = generate_assessments(
            self.skill,
            topics=topics,
            train=self.split.train,
            count=10,
            settings=self.settings,
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
