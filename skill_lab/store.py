from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Assessment, SkillPackage, Split

ROOT = Path(__file__).resolve().parent.parent / "data" / "skill_lab" / "runs"


def new_run_id() -> str:
    return f"run_{secrets.token_hex(8)}"


def run_dir(run_id: str) -> Path:
    return ROOT / run_id


class RunStore:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or new_run_id()
        self.root = run_dir(self.run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self.write_json(
                "manifest.json",
                {"run_id": self.run_id, "created_at": _utc(), "steps": {}},
            )

    def path(self, *parts: str) -> Path:
        p = self.root.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, data: Any) -> Path:
        p = self.path(rel)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def write_text(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.write_text(text, encoding="utf-8")
        return p

    def save_assessments(self, items: list[Assessment]) -> Path:
        return self.write_json("01-assessments.json", [a.to_dict() for a in items])

    def save_split(self, split: Split) -> Path:
        return self.write_json("02-split.json", split.to_dict())

    def save_skill(self, package: SkillPackage, folder: str = "03-skill") -> Path:
        base = self.path(folder)
        for name, content in package.files.items():
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.write_json(f"{folder}/package.json", package.to_dict())
        self.mark_step(folder, {"files": list(package.files), "summary": package.summary})
        return base

    def save_generated(self, items: list[Assessment]) -> Path:
        # path() mkdirs parents of the *file*; use write_text so 04-generated/ exists.
        for a in items:
            self.write_text(f"04-generated/{a.id}.md", f"# {a.title}\n\n{a.body}\n")
        return self.write_json("04-generated/index.json", [a.to_dict() for a in items])

    def save_comparison(self, report: dict[str, Any]) -> Path:
        self.write_text("05-comparison/summary.md", str(report.get("summary_markdown") or ""))
        return self.write_json("05-comparison/report.json", report)

    def save_improver(self, text: str) -> Path:
        return self.write_text("06-improver/IMPROVER_SKILL.md", text)

    def mark_step(self, name: str, meta: dict[str, Any] | None = None) -> None:
        m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        m["steps"][name] = {"at": _utc(), **(meta or {})}
        m["updated_at"] = _utc()
        self.manifest_path.write_text(json.dumps(m, indent=2), encoding="utf-8")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()
