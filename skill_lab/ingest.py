from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Assessment

_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _title_from(body: str, fallback: str) -> str:
    m = _TITLE_RE.search(body)
    if m:
        return m.group(1).strip()[:120]
    first = body.strip().splitlines()[0] if body.strip() else fallback
    return first.strip("# ").strip()[:120] or fallback


def assessment_from_text(body: str, *, idx: int, source: str) -> Assessment:
    aid = f"asm_{idx:02d}"
    return Assessment(id=aid, title=_title_from(body, aid), body=body.strip(), source=source)


def parse_file(path: Path, *, start_idx: int) -> list[Assessment]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        items = data if isinstance(data, list) else data.get("assessments") or [data]
        out: list[Assessment] = []
        for i, item in enumerate(items):
            if isinstance(item, str):
                out.append(assessment_from_text(item, idx=start_idx + i, source=path.name))
            else:
                body = str(item.get("body") or item.get("content") or item.get("markdown") or "")
                title = str(item.get("title") or _title_from(body, f"asm_{start_idx + i:02d}"))
                out.append(
                    Assessment(
                        id=str(item.get("id") or f"asm_{start_idx + i:02d}"),
                        title=title,
                        body=body.strip(),
                        source=path.name,
                    )
                )
        return out
    # One file = one assessment. (Assessments often use --- horizontal rules;
    # multi-doc paste still splits on --- in parse_paste; JSON lists cover batches.)
    return [assessment_from_text(text, idx=start_idx, source=path.name)]


def parse_paste(text: str, *, start_idx: int = 1) -> list[Assessment]:
    text = text.strip()
    if not text:
        return []
    # Try JSON paste
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else data.get("assessments") or [data]
            out: list[Assessment] = []
            for i, item in enumerate(items):
                if isinstance(item, str):
                    out.append(assessment_from_text(item, idx=start_idx + i, source="paste"))
                else:
                    body = str(item.get("body") or item.get("content") or "")
                    out.append(
                        Assessment(
                            id=str(item.get("id") or f"asm_{start_idx + i:02d}"),
                            title=str(item.get("title") or _title_from(body, f"asm_{start_idx + i:02d}")),
                            body=body.strip(),
                            source="paste",
                        )
                    )
            return out
        except json.JSONDecodeError:
            pass
    chunks = [c.strip() for c in re.split(r"\n-{3,}\n", text) if c.strip()]
    return [assessment_from_text(c, idx=start_idx + i, source="paste") for i, c in enumerate(chunks)]


def require_twenty(items: list[Assessment]) -> list[Assessment]:
    if len(items) < 20:
        raise ValueError(f"Need exactly 20 assessments, got {len(items)}.")
    if len(items) > 20:
        return items[:20]
    return items
