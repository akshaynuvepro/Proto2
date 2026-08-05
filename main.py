#!/usr/bin/env python3
"""
Daily conversation extract + per-sandbox self-evolving skill update.

Sources:
  - LangSmith SME sessions (API extract)
  - Local coding agents via proto-capture MCP store (read-only materialize)

    uv run python main.py --project main
    uv run python main.py --project main extract --source all
    uv run python main.py --project main classify
    uv run python main.py --project main skills

Local capture is written in the background by the proto-capture MCP + skill/hooks.
This CLI only reads data/capture/conversations.json for --source local|all.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from analyze import DEFAULT_MODEL, analyze_day_with_llm, load_conversation_bundle_for_sessions
from classify import classify_today
from extract import ROOT, load_env, require_env, today_window, write_today_conversations
from extract_local import write_local_conversations
from skills import (
    DEFAULT_ANALYSIS_INSTRUCTIONS,
    analysis_skill_md_path,
    read_skill_body,
    skill_dir,
    update_skill_for_sandbox,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract today's conversations, classify by sandbox, and update per-sandbox skills."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "extract", "classify", "skills"],
        help="all=extract+classify+skills (default)",
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


def main() -> int:
    load_env()
    args = parse_args()
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    skills_root = Path(args.skills_output)

    today, _, _, _ = today_window()
    if args.date:
        today = date.fromisoformat(args.date)

    if args.command in {"all", "extract"}:
        if args.source in {"all", "langsmith"}:
            require_env("LANGSMITH_API_KEY")
            write_today_conversations(
                project=args.project,
                output_root=output_root,
                force=args.force,
                limit=args.limit,
                all_runs=args.all_runs,
            )
        if args.source in {"all", "local"}:
            write_local_conversations(day=today, output_root=output_root, force=args.force)

    conv_dirs = conversation_dirs(output_root, today)

    if args.command in {"all", "classify", "skills"}:
        if not conv_dirs:
            raise SystemExit(
                f"No conversations dirs for {today.isoformat()} under {output_root / 'conversations'}\n"
                "Run extract first (and ensure proto-capture MCP has written local sessions if using --source local)."
            )
        require_env("OPENROUTER_API_KEY")
        model = os.getenv("ANALYSIS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        api_key = os.environ["OPENROUTER_API_KEY"].strip()

        decisions = run_classify(
            conv_dirs=conv_dirs,
            skills_root=skills_root,
            output_root=output_root,
            day=today,
            model=model,
            api_key=api_key,
            force=args.force,
        )

        if args.command in {"all", "skills"}:
            run_skills(
                conv_dirs=conv_dirs,
                skills_root=skills_root,
                decisions=decisions,
                day=today,
                model=model,
                api_key=api_key,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
