"""Chainlit chat UI for the assessment skill lab."""

from __future__ import annotations

from pathlib import Path

import chainlit as cl

from openrouter import load_dotenv
from skill_lab.ingest import parse_file, parse_paste
from skill_lab.models import Assessment
from skill_lab.pipeline import Pipeline
from skill_lab.store import RunStore

load_dotenv()

WELCOME = """# Assessment Skill Lab

Paste or upload **20 approved SME assessments**, then run the agent-only loop:

1. Split 10 train / 10 holdout  
2. Create skill from train  
3. Generate 10 assessments  
4. SME comparator agent vs holdout  
5. Create improvement skill → improved skill  

**How to provide assessments**
- Upload `.md` / `.txt` / `.json` files (one assessment per file, or `---` separators / JSON list)
- Or paste markdown; separate assessments with a line of `---`

When you have 20, click **Start pipeline** (or send `start`).
"""


def _pipe() -> Pipeline:
    p = cl.user_session.get("pipeline")
    if p is None:
        p = Pipeline(store=RunStore())
        cl.user_session.set("pipeline", p)
        cl.user_session.set("collected", [])
    return p


def _collected() -> list[Assessment]:
    return list(cl.user_session.get("collected") or [])


def _set_collected(items: list[Assessment]) -> None:
    cl.user_session.set("collected", items)


async def _file_element(path: Path, name: str | None = None) -> cl.File:
    return cl.File(path=str(path), name=name or path.name, display="inline")


@cl.on_chat_start
async def on_chat_start() -> None:
    _pipe()
    _set_collected([])
    actions = [
        cl.Action(name="start_pipeline", payload={"op": "start"}, label="Start pipeline"),
        cl.Action(name="reset", payload={"op": "reset"}, label="Reset"),
    ]
    await cl.Message(content=WELCOME, actions=actions).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = (message.content or "").strip()
    collected = _collected()

    # Ingest uploads
    for el in message.elements or []:
        path = Path(getattr(el, "path", "") or "")
        if not path.exists():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".json", ".markdown"}:
            await cl.Message(content=f"Skipped unsupported file: {path.name}").send()
            continue
        parsed = parse_file(path, start_idx=len(collected) + 1)
        collected.extend(parsed)

    if text and text.lower() not in {"start", "go", "run", "reset"}:
        parsed = parse_paste(text, start_idx=len(collected) + 1)
        collected.extend(parsed)

    _set_collected(collected)

    if text.lower() == "reset":
        await _do_reset()
        return

    if text.lower() in {"start", "go", "run"}:
        await _run_full_pipeline()
        return

    n = len(collected)
    titles = "\n".join(f"- `{a.id}` {a.title}" for a in collected[-10:])
    more = "" if n <= 10 else f"\n…and {n - 10} earlier."
    msg = f"Collected **{n}/20** assessments.\n{titles}{more}"
    actions = []
    if n >= 20:
        msg += "\n\nReady. Click **Start pipeline** or send `start`."
        actions = [cl.Action(name="start_pipeline", payload={"op": "start"}, label="Start pipeline")]
    elif n > 0:
        msg += f"\n\nNeed **{20 - n}** more."
    await cl.Message(content=msg, actions=actions).send()


@cl.action_callback("start_pipeline")
async def on_start_pipeline(action: cl.Action) -> None:
    await _run_full_pipeline()


@cl.action_callback("reset")
async def on_reset(action: cl.Action) -> None:
    await _do_reset()


async def _do_reset() -> None:
    cl.user_session.set("pipeline", Pipeline(store=RunStore()))
    _set_collected([])
    await cl.Message(content="Session reset. Paste or upload 20 assessments.").send()


async def _run_full_pipeline() -> None:
    items = _collected()
    if len(items) < 20:
        await cl.Message(content=f"Need 20 assessments, have {len(items)}.").send()
        return
    if len(items) > 20:
        await cl.Message(content=f"Using first 20 of {len(items)}.").send()
        items = items[:20]
        _set_collected(items)

    pipe = _pipe()
    try:
        async with cl.Step(name="Split 10/10", type="tool") as step:
            split = await cl.make_async(pipe.set_assessments)(items)
            step.output = (
                f"seed={split.seed}\n\n"
                f"**Train ({len(split.train)})**\n"
                + "\n".join(f"- {a.id}: {a.title}" for a in split.train)
                + f"\n\n**Holdout ({len(split.holdout)})**\n"
                + "\n".join(f"- {a.id}: {a.title}" for a in split.holdout)
            )

        async with cl.Step(name="Create skill", type="llm") as step:
            skill = await cl.make_async(pipe.build_skill)()
            step.output = skill.summary or "(no summary)"
            skill_path = pipe.store.path("03-skill", "SKILL.md")
            await cl.Message(
                content=f"### Skill created\n\n{skill.summary}\n\n```markdown\n{skill.skill_md[:4000]}\n```",
                elements=[await _file_element(skill_path)],
            ).send()

        async with cl.Step(name="Generate 10 assessments", type="llm") as step:
            generated = await cl.make_async(pipe.generate)()
            step.output = "\n".join(f"- {a.id}: {a.title}" for a in generated)
            elements = []
            for a in generated[:3]:
                p = pipe.store.path("04-generated", f"{a.id}.md")
                elements.append(await _file_element(p))
            await cl.Message(
                content="### Generated assessments\n\n"
                + "\n".join(f"- **{a.id}**: {a.title}" for a in generated)
                + "\n\n(First 3 attached; all saved under the run folder.)",
                elements=elements,
            ).send()

        async with cl.Step(name="SME comparator (agent-only)", type="llm") as step:
            report = await cl.make_async(pipe.compare)()
            summary = str(report.get("summary_markdown") or "")
            score = report.get("overall_score")
            auto = report.get("automatic_metrics") or {}
            bleu = (auto.get("bleu") or {}).get("corpus")
            emb = (auto.get("embedding") or {}).get("mean_cosine")
            trace = report.get("agent_trace") or []
            tools_line = ", ".join(f"{t.get('tool')}{'✓' if t.get('ok') else '✗'}" for t in trace) or "(none)"
            metrics_line = f"SME={score} | BLEU corpus={bleu} | embed mean cos={emb}\nTools: {tools_line}"
            step.output = f"{metrics_line}\n\n{summary[:2000]}"
            report_path = pipe.store.path("05-comparison", "report.json")
            await cl.Message(
                content=(
                    f"### Comparison report\n\n"
                    f"**Overall SME score:** {score}  \n"
                    f"**BLEU (corpus):** {bleu}  \n"
                    f"**Embedding mean cosine:** {emb}  \n"
                    f"**Tools used:** {tools_line}\n\n"
                    f"{summary}"
                ),
                elements=[await _file_element(report_path)],
            ).send()

        async with cl.Step(name="Improvement skill + improved skill", type="llm") as step:
            improver, improved = await cl.make_async(pipe.improve)()
            step.output = improved.summary or "(no summary)"
            improver_path = pipe.store.path("06-improver", "IMPROVER_SKILL.md")
            improved_path = pipe.store.path("07-improved-skill", "SKILL.md")
            await cl.Message(
                content=(
                    "### Improvement skill\n\n"
                    f"```markdown\n{improver[:3000]}\n```\n\n"
                    f"### Improved skill\n\n{improved.summary}\n\n"
                    f"```markdown\n{improved.skill_md[:4000]}\n```\n\n"
                    f"Run artifacts: `{pipe.store.root}`"
                ),
                elements=[
                    await _file_element(improver_path),
                    await _file_element(improved_path),
                ],
            ).send()
    except Exception as exc:  # noqa: BLE001 — surface LLM/API failures in chat
        await cl.Message(content=f"Pipeline failed: `{exc}`").send()
        return

    await cl.Message(
        content=(
            "Pipeline complete (agent-only — no human review gate).\n\n"
            "Send more assessments + `start` for another run, or click **Reset**."
        ),
        actions=[cl.Action(name="reset", payload={"op": "reset"}, label="Reset")],
    ).send()
