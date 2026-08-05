#!/usr/bin/env python3
"""
Conversation extract + per-sandbox self-evolving skill update.

Sources:
  - LangSmith SME sessions (API extract)
  - Local coding agents via proto-capture MCP store (read-only materialize)

One-shot:
    uv run python main.py --project main
    uv run python main.py extract --source all
    uv run python main.py classify
    uv run python main.py skills

Continuous worker (polls capture store + LangSmith):
    uv run python main.py worker --project main
    uv run python main.py worker --interval 120 --langsmith-interval 900

Local capture is written in the background by the proto-capture MCP + skill/hooks.
This CLI only reads data/capture/conversations.json for --source local|all.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import date, datetime
from pathlib import Path

from analyze import DEFAULT_MODEL, analyze_day_with_llm, load_conversation_bundle_for_sessions
from classify import classify_today
from extract import ROOT, load_env, require_env, today_window, write_today_conversations
from extract_local import store_path, write_local_conversations
from skills import (
    DEFAULT_ANALYSIS_INSTRUCTIONS,
    analysis_skill_md_path,
    read_skill_body,
    skill_dir,
    update_skill_for_sandbox,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract conversations, classify by sandbox, and update per-sandbox skills."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "extract", "classify", "skills", "worker"],
        help="all=extract+classify+skills (default); worker=continuous poll loop",
    )
    parser.add_argument("--project", default="main")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "langsmith"),
        help="Root output dir (conversations/ and classification/ live under this)",
    )
    parser.add_argument(
        "--skills-output",
        default=str(ROOT / "data" / "skills"),
        help="Root dir for per-sandbox skills",
    )
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD) for classify/skills")
    parser.add_argument("--limit", type=int, default=None, help="Max LangSmith sessions to extract")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files / re-run classify")
    parser.add_argument("--all-runs", action="store_true")
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "langsmith", "local"],
        help="Which conversation sources to extract (default all)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("WORKER_INTERVAL", "120")),
        help="Worker: seconds between store polls (default 120)",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=float(os.getenv("WORKER_DEBOUNCE", "20")),
        help="Worker: wait until store fingerprint is stable this many seconds (default 20)",
    )
    parser.add_argument(
        "--langsmith-interval",
        type=float,
        default=float(os.getenv("WORKER_LANGSMITH_INTERVAL", "900")),
        help="Worker: seconds between LangSmith extracts (default 900)",
    )
    parser.add_argument(
        "--no-run-on-start",
        action="store_true",
        help="Worker: skip the immediate first run; only react to later changes",
    )
    return parser.parse_args()


def conversation_dirs(output_root: Path, day: date) -> list[Path]:
    """Dirs that may hold today's session MD files (new nested + legacy flat)."""
    day_s = day.isoformat()
    candidates = [
        output_root / "conversations" / "langsmith" / day_s,
        output_root / "conversations" / "local" / day_s,
        output_root / "conversations" / day_s,  # legacy Proto2 layout
    ]
    return [p for p in candidates if p.is_dir()]


def run_classify(
    *,
    conv_dirs: list[Path],
    skills_root: Path,
    output_root: Path,
    day: date,
    model: str,
    api_key: str,
    force: bool,
) -> dict:
    audit_path = output_root / "classification" / f"{day.isoformat()}.json"
    if audit_path.exists() and not force:
        print(f"reusing existing classification audit {audit_path}")
        return {sid: d for sid, d in json.loads(audit_path.read_text(encoding="utf-8"))["sessions"].items()}
    return classify_today(
        conv_dirs=conv_dirs,
        skills_root=skills_root,
        output_root=output_root,
        day=day,
        model=model,
        api_key=api_key,
    )


def run_skills(
    *,
    conv_dirs: list[Path],
    skills_root: Path,
    decisions: dict,
    day: date,
    model: str,
    api_key: str,
) -> None:
    by_slug: dict[str, dict] = {}
    for session_id, info in decisions.items():
        entry = by_slug.setdefault(
            info["slug"],
            {"name": info["name"], "description": info["description"], "session_ids": []},
        )
        entry["session_ids"].append(session_id)

    print(f"Updating skills for {len(by_slug)} sandbox(es)...")
    for slug, entry in by_slug.items():
        bundle, session_count, truncated = load_conversation_bundle_for_sessions(
            conv_dirs, entry["session_ids"]
        )
        if truncated:
            print(f"warning: bundle truncated for sandbox {slug}")

        analysis_skill = read_skill_body(analysis_skill_md_path(skills_root, slug))
        legacy_instructions_path = skill_dir(skills_root, slug) / "analysis_instructions.md"
        if analysis_skill is not None:
            instructions = analysis_skill[1]
        elif legacy_instructions_path.exists():
            instructions = legacy_instructions_path.read_text(encoding="utf-8")
        else:
            instructions = DEFAULT_ANALYSIS_INSTRUCTIONS

        print(f"Analyzing {session_count} session(s) for sandbox '{entry['name']}' ({slug})...")
        feedback = analyze_day_with_llm(bundle, model=model, api_key=api_key, system_prompt=instructions)

        update_skill_for_sandbox(
            slug=slug,
            name=entry["name"],
            description=entry["description"],
            feedback=feedback,
            session_count_today=session_count,
            active_date=day.isoformat(),
            skills_root=skills_root,
            model=model,
            api_key=api_key,
        )
        print(f"updated skill -> {skills_root / slug / 'SKILL.md'}")


def resolve_day(override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    today, _, _, _ = today_window()
    return today


def run_pipeline(
    *,
    command: str,
    project: str,
    output_root: Path,
    skills_root: Path,
    day: date,
    source: str,
    force: bool,
    limit: int | None,
    all_runs: bool,
) -> None:
    """Run extract / classify / skills once. Raises on hard config errors."""
    if command in {"all", "extract"}:
        if source in {"all", "langsmith"}:
            require_env("LANGSMITH_API_KEY")
            write_today_conversations(
                project=project,
                output_root=output_root,
                force=force,
                limit=limit,
                all_runs=all_runs,
            )
        if source in {"all", "local"}:
            write_local_conversations(day=day, output_root=output_root, force=force)

    conv_dirs = conversation_dirs(output_root, day)

    if command in {"all", "classify", "skills"}:
        if not conv_dirs:
            raise SystemExit(
                f"No conversations dirs for {day.isoformat()} under {output_root / 'conversations'}\n"
                "Run extract first (and ensure proto-capture MCP has written local sessions if using --source local)."
            )
        require_env("OPENROUTER_API_KEY")
        model = os.getenv("ANALYSIS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        api_key = os.environ["OPENROUTER_API_KEY"].strip()

        decisions = run_classify(
            conv_dirs=conv_dirs,
            skills_root=skills_root,
            output_root=output_root,
            day=day,
            model=model,
            api_key=api_key,
            force=force,
        )

        if command in {"all", "skills"}:
            run_skills(
                conv_dirs=conv_dirs,
                skills_root=skills_root,
                decisions=decisions,
                day=day,
                model=model,
                api_key=api_key,
            )


def local_store_fingerprint() -> str:
    path = store_path()
    if not path.exists():
        return f"missing:{path}"
    st = path.stat()
    return f"{path.resolve()}:{st.st_mtime_ns}:{st.st_size}"


def _log(msg: str) -> None:
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    print(f"[{ts}] {msg}", flush=True)


def wait_until_stable(debounce: float) -> str:
    """Return fingerprint after it stops changing for `debounce` seconds."""
    fp = local_store_fingerprint()
    if debounce <= 0:
        return fp
    last_change = time.monotonic()
    while True:
        time.sleep(min(2.0, max(0.5, debounce / 4)))
        now_fp = local_store_fingerprint()
        if now_fp != fp:
            fp = now_fp
            last_change = time.monotonic()
            _log(f"store still changing; debounce reset ({fp})")
            continue
        if time.monotonic() - last_change >= debounce:
            return fp


def run_worker(args: argparse.Namespace) -> int:
    load_env()
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    skills_root = Path(args.skills_output)
    source = args.source

    if source in {"all", "langsmith"}:
        require_env("LANGSMITH_API_KEY")
    if source in {"all", "local", "langsmith"}:
        # classify/skills always need OpenRouter once conversations exist
        require_env("OPENROUTER_API_KEY")

    interval = max(5.0, float(args.interval))
    debounce = max(0.0, float(args.debounce))
    langsmith_interval = max(60.0, float(args.langsmith_interval))

    last_fp = local_store_fingerprint()
    last_langsmith = 0.0
    pending_local = not args.no_run_on_start
    pending_langsmith = (not args.no_run_on_start) and source in {"all", "langsmith"}

    _log(
        "worker started "
        f"(interval={interval}s debounce={debounce}s langsmith_interval={langsmith_interval}s "
        f"source={source} store={store_path()})"
    )

    while True:
        try:
            day = resolve_day(args.date)
            fp = local_store_fingerprint()

            if source in {"all", "local"} and fp != last_fp:
                _log(f"local store change detected ({fp})")
                pending_local = True
                last_fp = fp

            now = time.monotonic()
            if source in {"all", "langsmith"} and (now - last_langsmith) >= langsmith_interval:
                pending_langsmith = True

            if pending_local or pending_langsmith:
                if pending_local and source in {"all", "local"}:
                    fp = wait_until_stable(debounce)
                    last_fp = fp

                run_source = source
                if pending_local and not pending_langsmith and source == "all":
                    run_source = "local"
                elif pending_langsmith and not pending_local and source == "all":
                    run_source = "langsmith"

                ran_local = pending_local and source in {"all", "local"}
                ran_langsmith = pending_langsmith and source in {"all", "langsmith"}
                processed_fp = last_fp

                _log(f"pipeline run starting (source={run_source}, day={day.isoformat()}, force=True)")
                try:
                    run_pipeline(
                        command="all",
                        project=args.project,
                        output_root=output_root,
                        skills_root=skills_root,
                        day=day,
                        source=run_source,
                        force=True,
                        limit=args.limit,
                        all_runs=args.all_runs,
                    )
                    _log("pipeline run finished")
                except SystemExit as e:
                    # empty day / missing conv dirs — keep worker alive
                    _log(f"pipeline skipped: {e}")
                except Exception:
                    _log("pipeline error (will retry on next trigger):\n" + traceback.format_exc())

                if ran_langsmith:
                    last_langsmith = time.monotonic()

                # Mark what we processed; re-queue if the store moved again during the run.
                last_fp = processed_fp
                pending_local = False
                pending_langsmith = False
                after_fp = local_store_fingerprint()
                if ran_local and after_fp != processed_fp:
                    _log("local store changed during pipeline; queueing another run")
                    pending_local = True
                    last_fp = processed_fp
                else:
                    last_fp = after_fp

        except KeyboardInterrupt:
            _log("worker stopped")
            return 0
        except Exception:
            _log("worker loop error:\n" + traceback.format_exc())

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("worker stopped")
            return 0


def main() -> int:
    load_env()
    args = parse_args()

    if args.command == "worker":
        return run_worker(args)

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    skills_root = Path(args.skills_output)
    day = resolve_day(args.date)

    run_pipeline(
        command=args.command,
        project=args.project,
        output_root=output_root,
        skills_root=skills_root,
        day=day,
        source=args.source,
        force=args.force,
        limit=args.limit,
        all_runs=args.all_runs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
