"""Git-backed prompt registry. Langfuse is a mirror, never the source of truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schemas import content_hash


PROMPT_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "assessment_evolution"


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    text: str
    git_hash: str
    path: Path


def load_prompt(name: str) -> Prompt:
    if not name or Path(name).name != name:
        raise ValueError("prompt name must be one safe filename stem")
    path = PROMPT_ROOT / f"{name}.md"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return Prompt(name=name, text=text, git_hash=content_hash(text), path=path)


def list_prompts() -> list[Prompt]:
    return [load_prompt(path.stem) for path in sorted(PROMPT_ROOT.glob("*.md"))]
