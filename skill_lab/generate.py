from __future__ import annotations

from typing import Any, Callable

from openrouter import OpenRouterSettings, chat_completions

from .models import Assessment, SkillPackage

ProgressCb = Callable[[int, int, str], None]


def _topics_from_train(train: list[Assessment], n: int) -> list[str]:
    topics = [a.title for a in train]
    while len(topics) < n:
        topics.append(f"Variant assessment {len(topics) + 1}")
    return topics[:n]


def generate_assessments(
    skill: SkillPackage,
    *,
    topics: list[str] | None = None,
    train: list[Assessment] | None = None,
    count: int = 10,
    settings: OpenRouterSettings | None = None,
    id_prefix: str = "gen",
    progress_cb: ProgressCb | None = None,
) -> tuple[list[Assessment], list[dict[str, Any]]]:
    use_topics = topics or _topics_from_train(train or [], count)
    if len(use_topics) < count:
        use_topics = use_topics + [f"Assessment {i + 1}" for i in range(len(use_topics), count)]
    use_topics = use_topics[:count]

    skill_ctx = skill.combined_prompt()
    if len(skill_ctx) > 24_000:
        skill_ctx = skill_ctx[:24_000] + "\n...[truncated]"
    system = (
        "You write one complete learner-facing assessment in markdown, following the skill package.\n"
        "Include title, scenario, phases/tasks, marks guidance, and services/tech as appropriate.\n"
        "Output markdown only — no preamble. Keep under ~1500 words.\n\n"
        f"SKILL PACKAGE:\n{skill_ctx}"
    )
    out: list[Assessment] = []
    metas: list[dict[str, Any]] = []
    for i, topic in enumerate(use_topics, start=1):
        text, meta = chat_completions(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "Write one complete assessment. "
                        f"Topic / title inspiration: {topic}. "
                        "Make it distinct from other assessments in this set but keep the same "
                        "house style. Do not include collection or sequence numbering "
                        "(such as 'Assessment 3 of 10') in the title."
                    ),
                },
            ],
            settings=settings,
            max_tokens=6000,
        )
        aid = f"{id_prefix}_{i:02d}"
        title = topic.strip()[:120] or aid
        # Prefer first markdown H1 if present
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()[:120]
                break
        out.append(Assessment(id=aid, title=title, body=text.strip(), source="generated"))
        metas.append(meta)
        if progress_cb is not None:
            try:
                progress_cb(i, count, title)
            except Exception:  # noqa: BLE001 — progress display must never break generation
                pass
    return out, metas
