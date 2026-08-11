from __future__ import annotations

import json
from typing import Any

from openrouter import OpenRouterSettings, chat_completions, strip_code_fence

from .models import Assessment, SkillPackage

SYSTEM = """You author a compact agent skill package for writing assessments in the same house style as the training examples.

Return ONLY valid JSON (keep each file under ~1200 words; be concise):
{
  "summary": "1-3 sentence overview",
  "files": {
    "SKILL.md": "...",
    "references/house-style.md": "...",
    "references/structure.md": "...",
    "references/worked-patterns.md": "..."
  }
}

SKILL.md must include: when to use, ordered workflow, hard rules, and pointers to references.
Ground every rule in the provided training assessments. Do not invent unrelated domains.
Do not escape newlines as literal \\n sequences inside strings beyond normal JSON encoding.
"""


def _train_payload(train: list[Assessment], per_body: int = 1800, max_chars: int = 24_000) -> str:
    parts: list[str] = []
    used = 0
    for a in train:
        body = a.body if len(a.body) <= per_body else a.body[:per_body] + "\n...[truncated]"
        block = f"## {a.id}: {a.title}\n\n{body}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n---\n".join(parts)


def _parse_package(text: str) -> SkillPackage:
    raw = strip_code_fence(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Truncated/malformed model JSON → keep usable markdown skill
        return SkillPackage(files={"SKILL.md": raw}, summary="Parsed as markdown fallback (invalid JSON).")
    files = {str(k): str(v) for k, v in (data.get("files") or {}).items()}
    if "SKILL.md" not in files:
        files["SKILL.md"] = str(data.get("skill_md") or raw)
    return SkillPackage(files=files, summary=str(data.get("summary") or ""))


def create_skill(
    train: list[Assessment],
    *,
    settings: OpenRouterSettings | None = None,
) -> tuple[SkillPackage, dict[str, Any]]:
    user = (
        f"Create a compact skill package from these {len(train)} approved SME assessments "
        f"(training split). Keep total JSON well under output limits.\n\n{_train_payload(train)}"
    )
    text, meta = chat_completions(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        settings=settings,
        response_format={"type": "json_object"},
        max_tokens=12000,
    )
    package = _parse_package(text)
    if package.summary.startswith("Parsed as markdown fallback"):
        # one compact retry
        retry_user = (
            "Previous output was invalid/truncated JSON. Return a SHORTER valid JSON skill package "
            "with the same schema. Each file <= 600 words.\n\n"
            f"{_train_payload(train, per_body=900, max_chars=12_000)}"
        )
        text2, meta2 = chat_completions(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": retry_user},
            ],
            settings=settings,
            response_format={"type": "json_object"},
            max_tokens=8000,
        )
        package = _parse_package(text2)
        meta = {**meta, "retry": meta2}
    return package, meta
