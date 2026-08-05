"""Shared conversation markdown frontmatter + transcript rendering."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from extract import MAX_TRANSCRIPT_CHARS, build_transcript, get_tz, yaml_escape


def render_conversation_md(
    *,
    payload: dict[str, Any],
    project: str,
    day: date,
    source: str,
    source_tool: str | None = None,
) -> str:
    transcript, truncated = build_transcript(payload["messages"])
    runs = payload.get("source_run_ids") or []
    runs_yaml = "[" + ", ".join(f'"{yaml_escape(str(r))}"' for r in runs) + "]"
    extracted_at = datetime.now(get_tz()).isoformat()
    sid = payload["session_id"]
    tool = source_tool or source
    return "\n".join(
        [
            "---",
            f'session_id: "{yaml_escape(sid)}"',
            f'source: "{yaml_escape(source)}"',
            f'source_tool: "{yaml_escape(tool)}"',
            f'project: "{yaml_escape(project)}"',
            f'date: "{day.isoformat()}"',
            f'started_at: "{yaml_escape(payload.get("started_at") or "")}"',
            f'ended_at: "{yaml_escape(payload.get("ended_at") or "")}"',
            f'extracted_at: "{yaml_escape(extracted_at)}"',
            f"turn_count: {payload['turn_count']}",
            f"source_run_ids: {runs_yaml}",
            f"truncated: {str(truncated).lower()}",
            "---",
            "",
            f"# Conversation session `{sid}`",
            "",
            "## Transcript",
            "",
            transcript.strip() or "_Empty transcript_",
            "",
        ]
    )


def messages_from_store_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"role": str(r.get("role") or "user"), "content": str(r.get("text") or "")} for r in rows]


# re-export for callers that only need the constant via this module
__all__ = ["MAX_TRANSCRIPT_CHARS", "render_conversation_md", "messages_from_store_rows"]
