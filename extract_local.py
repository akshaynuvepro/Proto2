"""Materialize local MCP capture store into per-session conversation markdown.

Does not snapshot agent logs — the capture MCP / hooks / skill own writes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from conversation_schema import messages_from_store_rows, render_conversation_md
from extract import ROOT, safe_filename

DEFAULT_STORE = ROOT / "data" / "capture" / "conversations.json"
HOME_STORE = Path.home() / ".proto-capture" / "conversations.json"


def store_path(override: Path | None = None) -> Path:
    import os

    if override is not None:
        return override
    env = os.getenv("PROTO_CAPTURE_STORE", "").strip()
    if env:
        return Path(env)
    # Prefer project store, then globally deployed MCP home store.
    if DEFAULT_STORE.exists():
        return DEFAULT_STORE
    if HOME_STORE.exists():
        return HOME_STORE
    return DEFAULT_STORE


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"messages": [], "path": str(path), "count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"messages": [], "path": str(path), "count": 0}


def group_messages_for_day(messages: list[dict[str, Any]], day: date) -> dict[tuple[str, str], list[dict[str, Any]]]:
    day_s = day.isoformat()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        if str(msg.get("day") or "") != day_s:
            # fall back: prefix of ts
            ts = str(msg.get("ts") or "")
            if not ts.startswith(day_s):
                continue
        tool = str(msg.get("tool") or "live")
        session_id = str(msg.get("sessionId") or msg.get("session_id") or "unknown")
        groups[(tool, session_id)].append(msg)
    for rows in groups.values():
        rows.sort(key=lambda m: (str(m.get("ts") or ""), str(m.get("id") or "")))
    return dict(groups)


def write_local_conversations(
    *,
    day: date,
    output_root: Path,
    store: Path | None = None,
    force: bool = False,
) -> tuple[Path, int]:
    """Write local sessions for `day`. Returns (out_dir, session_count)."""
    path = store_path(store)
    data = load_store(path)
    messages = data.get("messages") if isinstance(data.get("messages"), list) else []
    groups = group_messages_for_day(messages, day)

    out_dir = output_root / "conversations" / "local" / day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not groups:
        print(
            f"No local conversations for {day.isoformat()} in {path}\n"
            "  Tip: configure proto-capture MCP + skill/hooks in your coding agent, "
            "then use the agent as usual. Local extract only reads the MCP store."
        )
        return out_dir, 0

    wrote = 0
    for (tool, session_id), rows in sorted(groups.items()):
        file_id = f"{tool}_{safe_filename(session_id)}"
        out_path = out_dir / f"{file_id}.md"
        if out_path.exists() and not force:
            print(f"skip existing {out_path.name}")
            continue
        msgs = messages_from_store_rows(rows)
        payload = {
            "session_id": file_id,
            "messages": msgs,
            "started_at": rows[0].get("ts"),
            "ended_at": rows[-1].get("ts"),
            "source_run_ids": [],
            "turn_count": len(msgs),
        }
        out_path.write_text(
            render_conversation_md(
                payload=payload,
                project=f"local-{tool}",
                day=day,
                source=tool if tool in {"claude", "codex", "opencode", "gemini", "live"} else "live",
                source_tool=tool,
            ),
            encoding="utf-8",
        )
        wrote += 1
        print(f"wrote {out_path}")

    print(f"Local extract done for {day.isoformat()}: {wrote} new file(s) in {out_dir} (store={path})")
    return out_dir, len(groups)
