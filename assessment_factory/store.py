"""Simple JSON-backed store for factory artifacts.

Records are immutable once written (keyed by content-addressed ids). Templates
and skills carry a mutable ``status`` plus an append-only ``reviews`` list, so
approval history is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .schema import (
    AssessmentRecord,
    SkillFile,
    Template,
)


class FactoryStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for name in ("records", "templates", "skills"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # ---- generic io -----------------------------------------------------
    def _write_json(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- records --------------------------------------------------------
    def put_record(self, record: AssessmentRecord) -> AssessmentRecord:
        record.finalize()
        self._write_json(self.root / "records" / f"{record.record_id}.json", record.to_dict())
        return record

    def get_record(self, record_id: str) -> AssessmentRecord:
        return AssessmentRecord.from_dict(
            self._read_json(self.root / "records" / f"{record_id}.json")
        )

    def list_records(self) -> list[AssessmentRecord]:
        out = []
        for path in sorted((self.root / "records").glob("*.json")):
            out.append(AssessmentRecord.from_dict(self._read_json(path)))
        return out

    # ---- templates ------------------------------------------------------
    def put_template(self, template: Template) -> Template:
        template.finalize()
        self._write_json(self.root / "templates" / f"{template.template_id}.json", template.to_dict())
        return template

    def get_template(self, template_id: str) -> Template:
        return Template.from_dict(
            self._read_json(self.root / "templates" / f"{template_id}.json")
        )

    def list_templates(self) -> list[Template]:
        return [
            Template.from_dict(self._read_json(p))
            for p in sorted((self.root / "templates").glob("*.json"))
        ]

    # ---- skills (multi-file packages) -----------------------------------
    def put_skill(self, skill: SkillFile) -> SkillFile:
        skill.finalize()
        self._write_json(self.root / "skills" / f"{skill.skill_id}.json", skill.to_dict())
        # materialize the package as a browsable directory
        pkg = self.root / "skills" / skill.skill_id
        pkg.mkdir(parents=True, exist_ok=True)
        for rel, content in skill.files.items():
            fp = pkg / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        return skill

    def get_skill(self, skill_id: str) -> SkillFile:
        return SkillFile.from_dict(
            self._read_json(self.root / "skills" / f"{skill_id}.json")
        )

    def list_skills(self) -> list[SkillFile]:
        return [
            SkillFile.from_dict(self._read_json(p))
            for p in sorted((self.root / "skills").glob("*.json"))
        ]
