"""LangSmith: fetch today's sessions and write one conversation MD each."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from langsmith import Client

ROOT = Path(__file__).resolve().parent
THREAD_METADATA_KEYS = ("thread_id", "session_id", "conversation_id")
MAX_TRANSCRIPT_CHARS = 900_000


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(*keys: str) -> None:
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing required env var(s): {', '.join(missing)}")


def get_tz():
    # ponytail: system local tz; no tzdata package needed on Windows
    return datetime.now().astimezone().tzinfo or timezone.utc


def today_window() -> tuple[date, datetime, datetime, date]:
    """Return (today, start, end, next_date) in local TZ."""
    tz = get_tz()
    today = datetime.now(tz).date()
    start = datetime.combine(today, time.min, tzinfo=tz)
    end = datetime.combine(today, time.max, tzinfo=tz)
    next_day = today + timedelta(days=1)
    return today, start, end, next_day


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def safe_filename(key: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", key).strip("_")
    return (cleaned or "session")[:150]


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def get_session_key(run: Any) -> str:
    metadata = getattr(run, "metadata", None) or {}
    for key in THREAD_METADATA_KEYS:
        if metadata.get(key):
            return str(metadata[key])
    return str(getattr(run, "trace_id", None) or run.id)


def extract_turn_messages(run: Any) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    inputs = run.inputs or {}
    outputs = run.outputs or {}

    if "messages" in inputs:
        msgs = inputs["messages"]
        if msgs and isinstance(msgs[0], list):
            msgs = msgs[0]
        for msg in msgs:
            if isinstance(msg, dict):
                role = str(msg.get("role") or msg.get("type") or "user")
                messages.append({"role": role, "content": as_text(msg.get("content", msg))})
            else:
                messages.append({"role": "user", "content": as_text(msg)})
    elif "input" in inputs:
        messages.append({"role": "user", "content": as_text(inputs["input"])})
    elif inputs:
        messages.append({"role": "user", "content": as_text(inputs)})

    if "choices" in outputs:
        for choice in outputs["choices"]:
            msg = choice.get("message", choice) if isinstance(choice, dict) else choice
            if isinstance(msg, dict):
                messages.append(
                    {
                        "role": str(msg.get("role") or "assistant"),
                        "content": as_text(msg.get("content", msg)),
                    }
                )
            else:
                messages.append({"role": "assistant", "content": as_text(msg)})
    elif "generations" in outputs:
        gens = outputs["generations"]
        flat = gens[0] if gens and isinstance(gens[0], list) else gens
        for gen in flat:
            if isinstance(gen, dict):
                content = gen.get("text") or (gen.get("message") or {}).get("content") or gen
                messages.append({"role": "assistant", "content": as_text(content)})
            else:
                messages.append({"role": "assistant", "content": as_text(gen)})
    elif "completion" in outputs:
        messages.append({"role": "assistant", "content": as_text(outputs["completion"])})
    elif "output" in outputs:
        messages.append({"role": "assistant", "content": as_text(outputs["output"])})
    elif outputs:
        messages.append({"role": "assistant", "content": as_text(outputs)})

    return messages


def build_transcript(messages: list[dict[str, str]]) -> tuple[str, bool]:
    parts = [f"[{i}] {msg['role'].upper()}:\n{msg['content']}" for i, msg in enumerate(messages, 1)]
    transcript = "\n\n".join(parts)
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript, False
    return (
        transcript[:MAX_TRANSCRIPT_CHARS] + "\n\n[TRUNCATED: transcript exceeded limit]",
        True,
    )


def fetch_sessions(
    *,
    project: str,
    start_time: datetime,
    end_time: datetime,
    all_runs: bool = False,
) -> dict[str, list[Any]]:
    client = Client()
    kwargs: dict[str, Any] = {
        "project_name": project,
        "start_time": start_time,
        "end_time": end_time,
    }
    if not all_runs:
        kwargs["is_root"] = True

    # ponytail: list_runs still works; migrate to client.runs.query later
    print(
        f"Fetching runs from '{project}' "
        f"({start_time.isoformat()} -> {end_time.isoformat()})..."
    )
    runs = list(client.list_runs(**kwargs))
    print(f"Fetched {len(runs)} runs. Grouping into sessions...")

    sessions: dict[str, list[Any]] = defaultdict(list)
    for run in runs:
        sessions[get_session_key(run)].append(run)

    for session_runs in sessions.values():
        session_runs.sort(
            key=lambda r: r.start_time or datetime.min.replace(tzinfo=get_tz())
        )
    return dict(sessions)


def build_session_payload(session_id: str, runs: list[Any]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    for run in runs:
        messages.extend(extract_turn_messages(run))
    started = runs[0].start_time if runs else None
    ended = None
    for run in runs:
        ts = getattr(run, "end_time", None) or run.start_time
        if ts and (ended is None or ts > ended):
            ended = ts
    return {
        "session_id": session_id,
        "messages": messages,
        "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else None,
        "source_run_ids": [str(run.id) for run in runs],
        "turn_count": len(runs),
    }


def render_conversation_md(
    *,
    payload: dict[str, Any],
    project: str,
    day: date,
    source: str = "langsmith",
    source_tool: str | None = None,
) -> str:
    from conversation_schema import render_conversation_md as _render

    return _render(
        payload=payload,
        project=project,
        day=day,
        source=source,
        source_tool=source_tool or source,
    )


def write_today_conversations(
    *,
    project: str,
    output_root: Path,
    force: bool = False,
    limit: int | None = None,
    all_runs: bool = False,
) -> tuple[date, date, Path, int]:
    """Extract today's sessions to per-session MD files. Returns (today, next_day, dir, count)."""
    today, start, end, next_day = today_window()
    # Prefer nested langsmith/ layout; keep flat conversations/YYYY-MM-DD for old data.
    out_dir = output_root / "conversations" / "langsmith" / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    sessions = fetch_sessions(
        project=project,
        start_time=start,
        end_time=end,
        all_runs=all_runs,
    )
    items = sorted(sessions.items(), key=lambda kv: kv[0])
    if limit is not None:
        items = items[: max(0, limit)]

    wrote = 0
    for session_id, runs in items:
        path = out_dir / f"{safe_filename(session_id)}.md"
        if path.exists() and not force:
            print(f"skip existing {path.name}")
            continue
        payload = build_session_payload(session_id, runs)
        path.write_text(
            render_conversation_md(
                payload=payload,
                project=project,
                day=today,
                source="langsmith",
                source_tool="langsmith",
            ),
            encoding="utf-8",
        )
        wrote += 1
        print(f"wrote {path}")

    print(f"Extraction done for {today.isoformat()}: {wrote} new file(s) in {out_dir}")
    return today, next_day, out_dir, len(items)
