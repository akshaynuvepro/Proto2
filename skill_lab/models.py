from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Assessment:
    id: str
    title: str
    body: str
    source: str = "paste"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Assessment":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or data["id"]),
            body=str(data.get("body") or ""),
            source=str(data.get("source") or "paste"),
        )


@dataclass(slots=True)
class Split:
    train: list[Assessment]
    holdout: list[Assessment]
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "train": [a.to_dict() for a in self.train],
            "holdout": [a.to_dict() for a in self.holdout],
        }


@dataclass(slots=True)
class SkillPackage:
    files: dict[str, str] = field(default_factory=dict)
    summary: str = ""

    @property
    def skill_md(self) -> str:
        return self.files.get("SKILL.md", "")

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "files": self.files}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillPackage":
        return cls(
            files=dict(data.get("files") or {}),
            summary=str(data.get("summary") or ""),
        )

    def combined_prompt(self) -> str:
        parts = []
        for path in sorted(self.files):
            parts.append(f"### FILE: {path}\n\n{self.files[path]}")
        return "\n\n".join(parts)
