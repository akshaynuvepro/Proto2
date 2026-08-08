"""Versioned split loader with leakage-group isolation checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import BenchmarkItem, SchemaError, content_hash

try:
    from skillopt.datasets.base import SplitDataLoader

    SKILLOPT_AVAILABLE = True
except ImportError:
    SplitDataLoader = object  # type: ignore[assignment,misc]
    SKILLOPT_AVAILABLE = False


class AssessmentImproverDataLoader(SplitDataLoader):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not SKILLOPT_AVAILABLE:
            raise RuntimeError(
                "SkillOpt 0.2.0 is required; install the assessment-evolution dependencies"
            )
        super().__init__(*args, **kwargs)

    def load_split_items(self, split_path: str) -> list[dict[str, Any]]:
        files = sorted(Path(split_path).glob("*.json"))
        if not files:
            raise FileNotFoundError(f"no benchmark JSON found in {split_path}")
        out: list[dict[str, Any]] = []
        ids: set[str] = set()
        groups: set[str] = set()
        hashes: set[str] = set()
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else [raw]
            for supplied in rows:
                item = BenchmarkItem.from_dict(supplied)
                if item.id in ids:
                    raise SchemaError(f"duplicate benchmark ID {item.id}")
                if item.split_group in groups:
                    raise SchemaError(
                        f"split group {item.split_group} appears more than once in one split"
                    )
                normalized_hash = content_hash(
                    {
                        "target": item.target_skill_envelope.get("input_content_hash"),
                        "brief": item.assessment_brief,
                    }
                )
                if normalized_hash in hashes:
                    raise SchemaError("near-identical target/brief fixture detected")
                ids.add(item.id)
                groups.add(item.split_group)
                hashes.add(normalized_hash)
                normalized = item.to_dict()
                normalized["task_type"] = str(
                    item.metadata.get("assessment_type") or "assessment-evolution"
                )
                out.append(normalized)
        return out

    def setup(self, cfg: dict[str, Any]) -> None:
        super().setup(cfg)
        seen_groups: dict[str, str] = {}
        seen_content: dict[str, str] = {}
        for split_name, items in (
            ("train", self.train_items),
            ("validation", self.val_items),
            ("test", self.test_items),
        ):
            for item in items:
                group = str(item["split_group"])
                prior_split = seen_groups.get(group)
                if prior_split and prior_split != split_name:
                    raise SchemaError(
                        f"split group {group} leaks across {prior_split} and {split_name}"
                    )
                seen_groups[group] = split_name
                normalized_hash = content_hash(
                    {
                        "target": item["target_skill_envelope"].get("input_content_hash"),
                        "brief": item["assessment_brief"],
                    }
                )
                prior_content_split = seen_content.get(normalized_hash)
                if prior_content_split and prior_content_split != split_name:
                    raise SchemaError(
                        f"near-identical target/brief leaks across {prior_content_split} and {split_name}"
                    )
                seen_content[normalized_hash] = split_name
