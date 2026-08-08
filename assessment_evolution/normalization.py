"""Adapters from existing Proto2 captures to canonical conversations."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .schemas import ConversationRecord, content_hash, stable_id, utc_now


NORMALIZER_VERSION = "1.0.0"
_TRANSCRIPT_MESSAGE = re.compile(
    r"(?ms)^\[(\d+)\]\s+(SYSTEM|USER|ASSISTANT|TOOL):\r?\n(.*?)(?=^\[\d+\]\s+(?:SYSTEM|USER|ASSISTANT|TOOL):\r?\n|\Z)"
)


def _as_iso(value: Any, fallback: str | None = None) -> str:
    if value:
        raw = str(value)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return fallback or utc_now()


def _canonical_role(value: Any) -> str:
    role = str(value or "user").lower()
    aliases = {"human": "user", "ai": "assistant", "function": "tool"}
    role = aliases.get(role, role)
    return role if role in {"system", "user", "assistant", "tool"} else "user"


def pseudonym(prefix: str, raw: str) -> str:
    return stable_id(prefix, {"value": raw})


def normalize_messages(
    messages: Iterable[dict[str, Any]],
    *,
    persona: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(messages, 1):
        text = str(raw.get("content", raw.get("text", ""))).replace("\r\n", "\n").strip()
        if not text:
            continue
        role = _canonical_role(raw.get("role"))
        source_id = raw.get("id") or raw.get("source_message_id")
        message_id = stable_id(
            "msg",
            {
                "conversation_id": conversation_id,
                "sequence": index,
                "source_id": source_id,
                "content": text,
            },
        )
        speaker = raw.get("speaker_persona")
        if speaker not in {"sme", "learner", "agent", "system"}:
            if role in {"assistant", "tool"}:
                speaker = "agent"
            elif role == "system":
                speaker = "system"
            elif persona in {"sme", "learner"}:
                speaker = persona
            else:
                speaker = None
        timestamp_value = raw.get("timestamp") or raw.get("ts")
        out.append(
            {
                "message_id": message_id,
                "sequence": len(out) + 1,
                "role": role,
                "speaker_persona": speaker,
                "timestamp": _as_iso(timestamp_value) if timestamp_value else None,
                "content": text,
                "content_hash": content_hash(text),
                "source_message_id": str(source_id) if source_id is not None else None,
                "attachment_ids": list(raw.get("attachment_ids") or []),
                "redaction_state": "raw",
            }
        )
    return out


def normalize_conversation(
    *,
    source: str,
    source_conversation_id: str,
    messages: Iterable[dict[str, Any]],
    persona: str = "unknown",
    participant_ids: Iterable[str] = (),
    started_at: str | None = None,
    ended_at: str | None = None,
    source_uri: str | None = None,
    assessment_id: str | None = None,
    assessment_version: str | None = None,
    target_skill_id: str | None = None,
    domain: str | None = None,
    cohort_id: str | None = None,
    consent: dict[str, bool] | None = None,
    retention_class: str = "assessment-research-pending",
    metadata: dict[str, Any] | None = None,
) -> ConversationRecord:
    source_messages = list(messages)
    raw_for_hash = {
        "source": source,
        "source_conversation_id": source_conversation_id,
        "messages": source_messages,
    }
    conversation_id = stable_id(
        "conv", {"source": source, "source_conversation_id": source_conversation_id}
    )
    normalized_messages = normalize_messages(
        source_messages, persona=persona, conversation_id=conversation_id
    )
    timestamps = [m["timestamp"] for m in normalized_messages if m["timestamp"]]
    record = ConversationRecord(
        conversation_id=conversation_id,
        source=source,
        source_conversation_id=source_conversation_id,
        source_uri=source_uri,
        source_hash=content_hash(raw_for_hash),
        persona=persona,
        participant_ids=[pseudonym("person", str(value)) for value in participant_ids],
        assessment_id=assessment_id,
        assessment_version=assessment_version,
        target_skill_id=target_skill_id,
        domain=domain,
        cohort_id=pseudonym("cohort", cohort_id) if cohort_id else None,
        started_at=_as_iso(started_at, timestamps[0] if timestamps else None),
        ended_at=_as_iso(ended_at, timestamps[-1]) if ended_at or timestamps else None,
        messages=normalized_messages,
        attachments=[],
        consent=consent
        or {
            "assessment_improvement": False,
            "llm_processing": False,
            "telemetry_redacted": False,
        },
        retention_class=retention_class,
        normalizer_version=NORMALIZER_VERSION,
        metadata=metadata or {},
    )
    record.validate()
    return record


def normalize_capture_store(
    path: Path,
    *,
    persona: str = "unknown",
    consent: dict[str, bool] | None = None,
    retention_class: str = "assessment-research-pending",
) -> list[ConversationRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for message in raw.get("messages") or []:
        tool = str(message.get("tool") or "live")
        source_id = str(message.get("sessionId") or message.get("session_id") or "unknown")
        groups[(tool, source_id)].append(message)
    records = []
    for (tool, source_id), messages in sorted(groups.items()):
        messages.sort(key=lambda row: (str(row.get("ts") or ""), str(row.get("id") or "")))
        participants = sorted(
            {
                str(row.get("participantId") or row.get("participant_id"))
                for row in messages
                if row.get("participantId") or row.get("participant_id")
            }
        )
        records.append(
            normalize_conversation(
                source=f"local-{tool}",
                source_conversation_id=source_id,
                messages=messages,
                persona=persona,
                participant_ids=participants,
                started_at=messages[0].get("ts") if messages else None,
                ended_at=messages[-1].get("ts") if messages else None,
                consent=consent,
                retention_class=retention_class,
                metadata={"source_tool": tool, "source_path_hash": content_hash(str(path.resolve()))},
            )
        )
    return records


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip('"')
    return values, text[end + 4 :].lstrip()


def normalize_conversation_markdown(
    path: Path,
    *,
    persona: str = "unknown",
    consent: dict[str, bool] | None = None,
    retention_class: str = "assessment-research-pending",
) -> ConversationRecord:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    metadata, body = _frontmatter(text)
    transcript = body.partition("## Transcript")[2] if "## Transcript" in body else body
    messages = [
        {"role": match.group(2).lower(), "content": match.group(3).strip()}
        for match in _TRANSCRIPT_MESSAGE.finditer(transcript)
    ]
    if not messages:
        messages = [{"role": "user", "content": transcript.strip() or "_Empty transcript_"}]
    source = metadata.get("source") or "markdown"
    source_id = metadata.get("session_id") or path.stem
    return normalize_conversation(
        source=source,
        source_conversation_id=source_id,
        messages=messages,
        persona=persona,
        started_at=metadata.get("started_at") or None,
        ended_at=metadata.get("ended_at") or None,
        consent=consent,
        retention_class=retention_class,
        metadata={
            "project": metadata.get("project"),
            "source_tool": metadata.get("source_tool"),
            "source_path_hash": content_hash(str(path.resolve())),
        },
    )


def render_markdown(record: ConversationRecord) -> str:
    record.validate()
    transcript = "\n\n".join(
        f"[{message['sequence']}] {message['role'].upper()}:\n{message['content']}"
        for message in record.messages
    )
    return (
        "---\n"
        f'schema_version: "{record.schema_version}"\n'
        f'conversation_id: "{record.conversation_id}"\n'
        f'source: "{record.source}"\n'
        f'persona: "{record.persona}"\n'
        f'source_hash: "{record.source_hash}"\n'
        "---\n\n"
        f"# Canonical Conversation {record.conversation_id}\n\n"
        "## Transcript\n\n"
        f"{transcript}\n"
    )
