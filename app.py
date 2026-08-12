"""Chainlit chat UI for the assessment skill lab — closed-loop edition.

UX model:
- Chat = concise progress + scores.
- Every document (skills, all generated assessments, reports) is a clickable
  side-panel element: click its name to read the FULL rendered markdown.
- `docs` / 📖 Documents re-opens the whole library of the current run anytime.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import chainlit as cl

from openrouter import load_dotenv
from skill_lab.ingest import parse_file, parse_paste
from skill_lab.models import Assessment
from skill_lab.pipeline import (
    NOISE_THRESHOLD,
    Pipeline,
    list_resumable_runs,
)
from skill_lab.runs_browser import (
    list_all_runs,
    load_run_bundle,
    report_markdown,
    stage_status_markdown,
)
from skill_lab.store import RunStore, run_dir

load_dotenv()

WELCOME = """# 🧪 Assessment Skill Lab — closed loop

Turn **20 approved SME assessments** into a **self-improving** authoring skill.

```
split ─ skill vN ─ generate ─ compare (baseline)
                                  │
        improved skill vN+1 ◀─ improver
                │
    re-generate ─ re-compare ─ Δ verdict ✅/➖/❌
```

**Provide assessments**
- 📎 Upload `.md` / `.txt` / `.json` (one per file, `---` separators, or a JSON list)
- ✍️ Or paste markdown separated by a `---` line

**Reading documents:** every skill, generated assessment and report appears as a
clickable name — click it to read the full document in the side panel.

**Commands**
| Command | Action |
|---|---|
| `start` | run the full closed loop on the 20 collected assessments |
| `resume <run_id>` | continue optimizing a previous run's improved skill |
| `runs` | run history — every run with progress, scores and status |
| `open <run_id>` | browse a past run stage-by-stage (all documents readable) |
| `docs` | re-open all documents of the current/opened run |
| `reset` | clear the session |
"""

# Chainlit can't infer a mime for text files (filetype.guess returns None for
# .md/.json), which serializes mime=null and crashes the frontend with
# "Cannot read properties of null (reading 'startsWith')". Set it explicitly.
_MIME_BY_EXT = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
    ".txt": "text/plain",
}

_VERDICT_STYLE = {
    "improved": ("✅", "IMPROVED — the delta is above the noise threshold."),
    "within_noise": ("➖", "NO PROVABLE CHANGE — the delta is inside judge noise."),
    "regressed": ("❌", "REGRESSED — the improved skill scored measurably worse."),
    "unknown": ("❓", "Scores missing — could not compute a verdict."),
}


# ---------------------------------------------------------------- session ----


def _collected() -> list[Assessment]:
    return list(cl.user_session.get("collected") or [])


def _set_collected(items: list[Assessment]) -> None:
    cl.user_session.set("collected", items)


# ------------------------------------------------------- document library ----


def _text_element(name: str, content: str) -> cl.Text:
    """Side-panel document: click the name in chat to read full markdown."""
    return cl.Text(name=name, content=content or "*(empty)*", display="side")


def _doc_index(groups: list[tuple[str, list[str]]]) -> cl.CustomElement:
    """Interactive document index (React): each doc is a button that opens the
    document in the side panel via the `read_doc` action. This avoids Chainlit's
    fragile element-name matching, which dumps full content inline on mismatch."""
    return cl.CustomElement(
        name="DocIndex",
        props={"groups": [{"title": t, "docs": names} for t, names in groups]},
        display="inline",
    )


async def _open_doc_in_sidebar(name: str, content: str) -> None:
    await cl.ElementSidebar.set_elements(
        [cl.Text(name=name, content=content or "*(empty)*", display="side")]
    )
    await cl.ElementSidebar.set_title(name[:60])


async def _file_element(path: Path, name: str | None = None) -> cl.File:
    mime = _MIME_BY_EXT.get(path.suffix.lower(), "text/plain")
    return cl.File(path=str(path), name=name or path.name, mime=mime, display="inline")


def _lib() -> list[dict]:
    return list(cl.user_session.get("doclib") or [])


def _lib_reset() -> None:
    cl.user_session.set("doclib", [])


def _lib_add(section: str, docs: list[tuple[str, str]]) -> None:
    lib = _lib()
    known = {d["name"] for d in lib}
    for name, content in docs:
        if name in known:
            continue
        lib.append({"section": section, "name": name, "content": content})
    cl.user_session.set("doclib", lib)


async def _send_docs_library() -> None:
    lib = _lib()
    if not lib:
        await cl.Message(
            content="No documents yet — run the pipeline first (`start`)."
        ).send()
        return
    sections: dict[str, list[str]] = {}
    for d in lib:
        sections.setdefault(d["section"], []).append(d["name"])
    await cl.Message(
        content="### 📖 Documents\n\nClick a document to read it in the side panel:",
        elements=[_doc_index(list(sections.items()))],
    ).send()


# ----------------------------------------------------------- formatting ----


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    return f"+{value}" if value > 0 else f"{value}"


def _scoreboard(delta: dict, base_gen: int) -> str:
    rows = [
        f"| Dimension | skill v{base_gen} | skill v{base_gen + 1} | Δ |",
        "|---|---|---|---|",
    ]
    for key, v in (delta.get("dimensions") or {}).items():
        rows.append(
            f"| {key} | {v.get('baseline', '—')} | {v.get('improved', '—')} | "
            f"{_fmt_delta(v.get('delta'))} |"
        )
    rows.append(
        f"| **overall** | **{delta.get('baseline_overall', '—')}** | "
        f"**{delta.get('improved_overall', '—')}** | "
        f"**{_fmt_delta(delta.get('delta_overall'))}** |"
    )
    return "\n".join(rows)


def _compare_summary_line(report: dict) -> str:
    auto = report.get("automatic_metrics") or {}
    bleu = (auto.get("bleu") or {}).get("corpus")
    emb = (auto.get("embedding") or {}).get("mean_cosine")
    dims = report.get("dimensions") or {}
    dim_line = " · ".join(
        f"{k} **{(v or {}).get('score', '—')}**" for k, v in dims.items()
    )
    return (
        f"**SME rubric score: {report.get('overall_score')} / 10**\n\n"
        f"{dim_line}\n\n"
        f"*Topic-drift indicators (not quality): BLEU {bleu} · embed cos {emb}*"
    )


def _skill_docs(prefix: str, files: dict[str, str]) -> list[tuple[str, str]]:
    order = ["SKILL.md"] + sorted(k for k in files if k != "SKILL.md")
    return [(f"{prefix} · {k}", files[k]) for k in order if k in files]


def _assessment_docs(items: list[Assessment]) -> list[tuple[str, str]]:
    return [(f"{a.id} · {a.title[:60]}", a.body) for a in items]


# -------------------------------------------------------------- handlers ----


@cl.on_chat_start
async def on_chat_start() -> None:
    # NOTE: no Pipeline/RunStore here — a run folder is only created when a
    # pipeline actually starts (avoids littering data/ with empty run dirs).
    _set_collected([])
    _lib_reset()
    actions = [
        cl.Action(name="start_pipeline", payload={"op": "start"}, label="▶ Start closed loop"),
        cl.Action(name="resume_latest", payload={"op": "resume"}, label="⟳ Resume latest run"),
        cl.Action(name="show_docs", payload={"op": "docs"}, label="📖 Documents"),
        cl.Action(name="list_runs", payload={"op": "runs"}, label="🗂 Runs"),
        cl.Action(name="reset", payload={"op": "reset"}, label="Reset"),
    ]
    await cl.Message(content=WELCOME, actions=actions).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = (message.content or "").strip()
    lower = text.lower()
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

    is_command = (
        lower in {"start", "go", "run", "reset", "runs", "docs"}
        or lower.startswith("resume")
        or lower.startswith("open")
        or lower.startswith("view")
    )
    if text and not is_command:
        parsed = parse_paste(text, start_idx=len(collected) + 1)
        collected.extend(parsed)

    _set_collected(collected)

    if lower == "reset":
        await _do_reset()
        return
    if lower == "runs":
        await _show_runs()
        return
    if lower == "docs":
        await _send_docs_library()
        return
    if lower.startswith("open") or lower.startswith("view"):
        run_id = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
        if not run_id:
            await _show_runs()
            return
        await _open_run(run_id)
        return
    if lower.startswith("resume"):
        run_id = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
        target = run_id or _latest_resumable()
        if not target:
            await cl.Message(
                content="No resumable runs yet — complete one closed-loop run first."
            ).send()
            return
        await _run_closed_loop(resume_run_id=target)
        return
    if lower in {"start", "go", "run"}:
        await _run_closed_loop()
        return

    n = len(collected)
    titles = "\n".join(f"- `{a.id}` {a.title}" for a in collected[-10:])
    more = "" if n <= 10 else f"\n…and {n - 10} earlier."
    msg = f"Collected **{n}/20** assessments.\n{titles}{more}"
    actions = []
    if n >= 20:
        msg += "\n\nReady. Click **Start closed loop** or send `start`."
        actions = [
            cl.Action(name="start_pipeline", payload={"op": "start"}, label="▶ Start closed loop")
        ]
    elif n > 0:
        msg += f"\n\nNeed **{20 - n}** more."
    await cl.Message(content=msg, actions=actions).send()


@cl.action_callback("start_pipeline")
async def on_start_pipeline(action: cl.Action) -> None:
    await _run_closed_loop()


@cl.action_callback("resume_latest")
async def on_resume_latest(action: cl.Action) -> None:
    target = _latest_resumable()
    if not target:
        await cl.Message(
            content="No resumable runs yet — complete one closed-loop run first."
        ).send()
        return
    await _run_closed_loop(resume_run_id=target)


@cl.action_callback("show_docs")
async def on_show_docs(action: cl.Action) -> None:
    await _send_docs_library()


@cl.action_callback("read_doc")
async def on_read_doc(action: cl.Action) -> None:
    name = str((action.payload or {}).get("doc") or "")
    for d in _lib():
        if d["name"] == name:
            await _open_doc_in_sidebar(name, d["content"])
            return
    await cl.Message(
        content=f"Document `{name}` is not loaded in this session — "
        "re-open its run (`runs` → click the run id)."
    ).send()


@cl.action_callback("open_run")
async def on_open_run(action: cl.Action) -> None:
    run_id = str((action.payload or {}).get("run_id") or "")
    if run_id:
        await _open_run(run_id)


@cl.action_callback("resume_run")
async def on_resume_run(action: cl.Action) -> None:
    run_id = str((action.payload or {}).get("run_id") or "")
    if run_id:
        await _run_closed_loop(resume_run_id=run_id)


@cl.action_callback("list_runs")
async def on_list_runs(action: cl.Action) -> None:
    await _show_runs()


@cl.action_callback("reset")
async def on_reset(action: cl.Action) -> None:
    await _do_reset()


async def _do_reset() -> None:
    cl.user_session.set("pipeline", None)
    _set_collected([])
    _lib_reset()
    await cl.Message(content="Session reset. Paste or upload 20 assessments.").send()


def _latest_resumable() -> str | None:
    runs = list_resumable_runs()
    return runs[0]["run_id"] if runs else None


def _run_status_text(r: dict) -> str:
    verdict_map = {
        "improved": "✅ improved",
        "within_noise": "➖ within noise",
        "regressed": "❌ regressed",
    }
    if r.get("verdict"):
        return verdict_map.get(r["verdict"], str(r["verdict"]))
    if r.get("status") == "completed":
        return "✅ completed"
    if r.get("status") == "empty":
        return "⚪ empty"
    return f"⚠ {r.get('status')}"


async def _show_runs() -> None:
    runs = list_all_runs()
    runs = [r for r in runs if r.get("status") != "empty"]
    if not runs:
        await cl.Message(content="No runs on disk yet — run the pipeline first (`start`).").send()
        return

    runs_props = []
    for r in runs:
        gen = r["skill_generation"]
        improved = "improve" in (r.get("stages_done") or [])
        runs_props.append(
            {
                "run_id": r["run_id"],
                "skill": f"v{gen}→v{gen + 1}" if improved else f"v{gen}",
                "progress": f"{len(r.get('stages_done') or [])}/6",
                "baseline": r.get("baseline"),
                "improved": r.get("improved"),
                "delta": _fmt_delta(r.get("delta")) if r.get("delta") is not None else None,
                "status": _run_status_text(r),
                "resumable": bool(r.get("resumable")),
            }
        )

    table = cl.CustomElement(name="RunsTable", props={"runs": runs_props}, display="inline")
    await cl.Message(
        content=(
            "### 🗂 Run history\n\n"
            "Click a **run id** to open the full run here in the chat "
            "(every stage and document readable). **⟳ Resume** continues optimizing "
            "that run's improved skill."
        ),
        elements=[table],
    ).send()


async def _open_run(run_id: str) -> None:
    """Browse a past run stage-by-stage; all documents readable in the side panel."""
    try:
        bundle = load_run_bundle(run_id)
    except FileNotFoundError:
        await cl.Message(
            content=f"Run `{run_id}` not found. Send `runs` to list available runs."
        ).send()
        return

    m = bundle["manifest"]
    gen = bundle["skill_generation"]
    lineage = f" · resumed from `{m.get('resumed_from')}`" if m.get("resumed_from") else ""

    # Side panel: stages + status only (mirrors the live pipeline task tracker).
    try:
        await cl.ElementSidebar.set_elements(
            [
                cl.Text(
                    name=f"Stages — {run_id}",
                    content=stage_status_markdown(run_id),
                    display="side",
                )
            ],
            key=run_id,
        )
        await cl.ElementSidebar.set_title(f"Stages · {run_id[-6:]}")
    except Exception:  # noqa: BLE001 — sidebar is a nice-to-have, never block the flow
        pass

    # Rebuild the document library; render ONE compact message with an
    # interactive doc index (React buttons) — no inline content dumps possible.
    _lib_reset()
    groups: list[tuple[str, list[str]]] = []
    for section in bundle["sections"]:
        docs = section.get("docs") or []
        if not docs:
            continue
        _lib_add(section["title"], docs)
        groups.append((section["title"], [n for n, _ in docs]))

    header = (
        f"## 📂 Run `{run_id}`\n\n"
        f"Created: {str(m.get('created_at') or '—')[:19]} · skill v{gen}{lineage}  \n"
        f"Stage status → side panel. Click any document to read it:"
    )
    verdict = bundle.get("verdict")
    if verdict:
        emoji, verdict_text = _VERDICT_STYLE.get(
            verdict.get("verdict", "unknown"), _VERDICT_STYLE["unknown"]
        )
        header += f"\n\n{emoji} **{verdict_text}** · Δ overall: {verdict.get('delta_overall', '—')}"

    actions = [cl.Action(name="list_runs", payload={"op": "runs"}, label="🗂 Back to runs")]
    if (run_dir(run_id) / "07-improved-skill" / "package.json").exists():
        actions.insert(
            0,
            cl.Action(
                name="resume_run",
                payload={"run_id": run_id},
                label="⟳ Resume from this run",
            ),
        )
    await cl.Message(
        content=header,
        elements=[_doc_index(groups)],
        actions=actions,
    ).send()


# ---------------------------------------------------------- closed loop ----


async def _run_closed_loop(resume_run_id: str | None = None) -> None:
    resumed = bool(resume_run_id)

    if not resumed:
        items = _collected()
        if len(items) < 20:
            await cl.Message(content=f"Need 20 assessments, have {len(items)}.").send()
            return
        if len(items) > 20:
            await cl.Message(content=f"Using first 20 of {len(items)}.").send()
            items = items[:20]
            _set_collected(items)

    # Always run in a fresh Pipeline (fresh run folder) so reruns never
    # overwrite a previous run's artifacts.
    pipe = Pipeline(store=RunStore())
    cl.user_session.set("pipeline", pipe)
    _lib_reset()

    # ---- live task tracker ----
    labels = [
        "Load prior run" if resumed else "Split 10 train / 10 holdout",
        "Load improved skill" if resumed else "Create skill v1",
        "Generate 10 (current skill)",
        "SME compare — baseline score",
        "Improver → improved skill",
        "Re-generate 10 (improved skill)",
        "SME re-compare — improved score",
        "Δ verdict",
    ]
    tl = cl.TaskList(status="Running…")
    tasks = [cl.Task(title=t) for t in labels]
    for t in tasks:
        await tl.add_task(t)
    await tl.send()

    loop = asyncio.get_running_loop()

    def _gen_progress(task: cl.Task, base_label: str):
        def cb(i: int, n: int, title: str) -> None:
            async def _update() -> None:
                task.title = f"{base_label} — {i}/{n}: {title[:40]}"
                await tl.send()

            asyncio.run_coroutine_threadsafe(_update(), loop)

        return cb

    async def _stage(idx: int, fn):
        tasks[idx].status = cl.TaskStatus.RUNNING
        await tl.send()
        try:
            result = await fn()
        except Exception:
            tasks[idx].status = cl.TaskStatus.FAILED
            tl.status = "Failed"
            await tl.send()
            raise
        tasks[idx].status = cl.TaskStatus.DONE
        await tl.send()
        return result

    try:
        # 1 — split / adopt
        if resumed:
            split, skill = await _stage(
                0, lambda: cl.make_async(pipe.adopt_prior_run)(resume_run_id)
            )
            await cl.Message(
                content=(
                    f"### ⟳ Resumed from `{resume_run_id}`\n\n"
                    f"Continuing **skill v{pipe.skill_generation}** on the same "
                    f"10/10 split (seed `{split.seed}`)."
                )
            ).send()
        else:
            split = await _stage(0, lambda: cl.make_async(pipe.set_assessments)(items))
            await cl.Message(
                content=(
                    f"### Split (seed `{split.seed}`)\n\n"
                    f"**Train (10):** {', '.join(a.id for a in split.train)}\n\n"
                    f"**Holdout (10):** {', '.join(a.id for a in split.holdout)}"
                )
            ).send()

        # 2 — skill
        skill = await _stage(1, lambda: cl.make_async(pipe.build_skill)())
        skill_label = f"skill v{pipe.skill_generation}"
        skill_docs = _skill_docs(skill_label, skill.files)
        skill_section = f"🧠 Skill v{pipe.skill_generation}"
        _lib_add(skill_section, skill_docs)
        await cl.Message(
            content=(
                f"### 🧠 Skill v{pipe.skill_generation}"
                + ("" if resumed else " created")
                + f"\n\n{skill.summary}"
            ),
            elements=[_doc_index([(skill_section, [n for n, _ in skill_docs])])],
        ).send()

        # 3 — generate (baseline)
        gen_cb = _gen_progress(tasks[2], labels[2])
        generated = await _stage(2, lambda: cl.make_async(pipe.generate)(progress_cb=gen_cb))
        gen_docs = _assessment_docs(generated)
        gen_section = f"📝 Generated with skill v{pipe.skill_generation}"
        _lib_add(gen_section, gen_docs)
        await cl.Message(
            content=f"### 📝 Generated with skill v{pipe.skill_generation}",
            elements=[_doc_index([(gen_section, [n for n, _ in gen_docs])])],
        ).send()

        # 4 — baseline compare
        report = await _stage(3, lambda: cl.make_async(pipe.compare)())
        base_report_doc = (
            f"Baseline report — skill v{pipe.skill_generation}",
            report_markdown(report, f"Baseline report — skill v{pipe.skill_generation}"),
        )
        _lib_add("📊 Reports", [base_report_doc])
        await cl.Message(
            content=(
                f"### 📊 Baseline score — skill v{pipe.skill_generation}\n\n"
                f"{_compare_summary_line(report)}"
            ),
            elements=[
                _doc_index([("📊 Reports", [base_report_doc[0]])]),
                await _file_element(pipe.store.path("05-comparison", "report.json")),
            ],
        ).send()

        # 5 — improve
        improver, improved = await _stage(4, lambda: cl.make_async(pipe.improve)())
        improved_label = f"skill v{pipe.skill_generation + 1}"
        improved_docs = [
            (f"IMPROVER_SKILL.md (v{pipe.skill_generation}→v{pipe.skill_generation + 1})", improver)
        ] + _skill_docs(improved_label, improved.files)
        improved_section = f"🔧 Improved skill v{pipe.skill_generation + 1}"
        _lib_add(improved_section, improved_docs)
        await cl.Message(
            content=(
                f"### 🔧 Improved skill v{pipe.skill_generation + 1}\n\n{improved.summary}"
            ),
            elements=[_doc_index([(improved_section, [n for n, _ in improved_docs])])],
        ).send()

        # 6+7 — verify: re-generate + re-compare (single pipeline call, two tasks)
        regen_cb = _gen_progress(tasks[5], labels[5])

        async def _verify():
            tasks[5].status = cl.TaskStatus.RUNNING
            await tl.send()

            def _after_regen() -> None:
                async def _u() -> None:
                    tasks[5].status = cl.TaskStatus.DONE
                    tasks[6].status = cl.TaskStatus.RUNNING
                    await tl.send()

                asyncio.run_coroutine_threadsafe(_u(), loop)

            def cb(i: int, n: int, title: str) -> None:
                regen_cb(i, n, title)
                if i == n:
                    _after_regen()

            return await cl.make_async(pipe.verify)(progress_cb=cb)

        try:
            regenerated, report2, delta = await _verify()
        except Exception:
            tasks[5].status = cl.TaskStatus.FAILED
            tasks[6].status = cl.TaskStatus.FAILED
            tl.status = "Failed"
            await tl.send()
            raise
        tasks[5].status = cl.TaskStatus.DONE
        tasks[6].status = cl.TaskStatus.DONE
        await tl.send()

        regen_docs = _assessment_docs(regenerated)
        regen_section = f"📝 Re-generated with skill v{pipe.skill_generation + 1}"
        _lib_add(regen_section, regen_docs)
        await cl.Message(
            content=f"### 📝 Re-generated with skill v{pipe.skill_generation + 1}",
            elements=[_doc_index([(regen_section, [n for n, _ in regen_docs])])],
        ).send()

        improved_report_doc = (
            f"Improved report — skill v{pipe.skill_generation + 1}",
            report_markdown(
                report2, f"Improved report — skill v{pipe.skill_generation + 1}"
            ),
        )
        _lib_add("📊 Reports", [improved_report_doc])
        await cl.Message(
            content=(
                f"### 📊 Improved score — skill v{pipe.skill_generation + 1}\n\n"
                f"{_compare_summary_line(report2)}"
            ),
            elements=[
                _doc_index([("📊 Reports", [improved_report_doc[0]])]),
                await _file_element(
                    pipe.store.path("09-improved-comparison", "report.json")
                ),
            ],
        ).send()

        # 8 — verdict
        tasks[7].status = cl.TaskStatus.RUNNING
        await tl.send()
        emoji, verdict_text = _VERDICT_STYLE.get(delta["verdict"], _VERDICT_STYLE["unknown"])
        base_gen = pipe.skill_generation
        verdict_doc = (
            "Verdict — scores & deltas",
            f"# Verdict\n\n**{verdict_text}**\n\n{_scoreboard(delta, base_gen)}\n\n"
            f"*Judge noise threshold: ±{NOISE_THRESHOLD}.*",
        )
        _lib_add("📊 Reports", [verdict_doc])
        await cl.Message(
            content=(
                f"## {emoji} Verdict: {verdict_text}\n\n"
                f"{_scoreboard(delta, base_gen)}\n\n"
                f"*Judge noise threshold: ±{NOISE_THRESHOLD} — deltas inside this band "
                f"are not conclusive.*\n\n"
                f"Run: `{pipe.store.run_id}` · artifacts: `{pipe.store.root}`\n\n"
                f"**Continue the loop:** send `resume {pipe.store.run_id}` to keep "
                f"optimizing skill v{base_gen + 1}."
            ),
            elements=[
                _doc_index([("📊 Reports", [verdict_doc[0]])]),
                await _file_element(pipe.store.path("10-verdict.json")),
            ],
        ).send()
        tasks[7].status = cl.TaskStatus.DONE
        tl.status = "Done ✔"
        await tl.send()

    except Exception as exc:  # noqa: BLE001 — surface LLM/API failures in chat
        await cl.Message(content=f"Pipeline failed: `{exc}`").send()
        return

    await cl.Message(
        content="Closed loop complete. Use **📖 Documents** to re-read anything.",
        actions=[
            cl.Action(name="show_docs", payload={"op": "docs"}, label="📖 Documents"),
            cl.Action(name="resume_latest", payload={"op": "resume"}, label="⟳ Iterate again"),
            cl.Action(name="list_runs", payload={"op": "runs"}, label="🗂 Runs"),
            cl.Action(name="reset", payload={"op": "reset"}, label="Reset"),
        ],
    ).send()
