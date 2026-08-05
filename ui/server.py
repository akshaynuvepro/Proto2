#!/usr/bin/env python3
"""Local Proto2 analysis UI. Stdlib only. Run: uv run python ui/server.py"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
DATA = ROOT / "data"
SKILLS = DATA / "skills"
LANGSMITH = DATA / "langsmith"
CAPTURE = DATA / "capture" / "conversations.json"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n\n?", re.DOTALL)
_PORT = 8765


def parse_frontmatter(text: str) -> dict:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith('"') and value.endswith('"'):
            fields[key] = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif re.fullmatch(r"-?\d+", value):
            fields[key] = int(value)
        else:
            fields[key] = value
    return fields


def conversation_dirs() -> list[tuple[str, Path]]:
    """Return (label, dir) for every day folder that has session MDs."""
    out: list[tuple[str, Path]] = []
    conv_root = LANGSMITH / "conversations"
    if not conv_root.exists():
        return out
    # nested: langsmith/YYYY-MM-DD, local/YYYY-MM-DD
    for source in ("langsmith", "local"):
        nested = conv_root / source
        if nested.is_dir():
            for day_dir in sorted(nested.iterdir(), reverse=True):
                if day_dir.is_dir() and list(day_dir.glob("*.md")):
                    out.append((f"{source}/{day_dir.name}", day_dir))
    # legacy flat YYYY-MM-DD
    for day_dir in sorted(conv_root.iterdir(), reverse=True):
        if day_dir.is_dir() and day_dir.name not in {"langsmith", "local"}:
            if list(day_dir.glob("*.md")):
                out.append((f"legacy/{day_dir.name}", day_dir))
    return out


def list_classification_dates() -> list[str]:
    d = LANGSMITH / "classification"
    if not d.exists():
        return []
    return sorted((p.stem for p in d.glob("*.json")), reverse=True)


def load_index() -> dict:
    path = SKILLS / "index.json"
    if not path.exists():
        return {"sandboxes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def api_overview() -> dict:
    index = load_index()
    sandboxes = index.get("sandboxes") or {}
    skill_rows = []
    for slug, meta in sandboxes.items():
        skill_rows.append(
            {
                "slug": slug,
                "name": meta.get("name") or slug,
                "session_count": int(meta.get("session_count") or 0),
                "last_active_date": meta.get("last_active_date") or "",
            }
        )
    skill_rows.sort(key=lambda r: (-r["session_count"], r["name"]))

    conv_dirs = conversation_dirs()
    conv_counts = {label: len(list(path.glob("*.md"))) for label, path in conv_dirs}

    capture = {"exists": CAPTURE.exists(), "count": 0, "updatedAt": None}
    if CAPTURE.exists():
        try:
            raw = json.loads(CAPTURE.read_text(encoding="utf-8"))
            msgs = raw.get("messages") or []
            capture["count"] = len(msgs)
            capture["updatedAt"] = raw.get("updatedAt")
            capture["byTool"] = dict(Counter(str(m.get("tool") or "unknown") for m in msgs))
            capture["byRole"] = dict(Counter(str(m.get("role") or "unknown") for m in msgs))
        except (OSError, json.JSONDecodeError):
            pass

    class_dates = list_classification_dates()
    class_summary = None
    if class_dates:
        full = api_classification(class_dates[0])
        if full:
            # Keep overview light — omit per-session rows.
            class_summary = {
                "date": full["date"],
                "generated_at": full.get("generated_at"),
                "session_count": full["session_count"],
                "new_sandbox_assignments": full["new_sandbox_assignments"],
                "by_slug": full["by_slug"][:15],
                "by_source": full["by_source"],
            }

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "totals": {
            "skills": len(skill_rows),
            "skillSessions": sum(r["session_count"] for r in skill_rows),
            "conversationFiles": sum(conv_counts.values()),
            "captureMessages": capture["count"],
            "classificationDays": len(class_dates),
        },
        "topSkills": skill_rows[:12],
        "conversationDirs": [{"label": k, "count": v} for k, v in conv_counts.items()],
        "classificationDates": class_dates,
        "latestClassification": class_summary,
        "capture": capture,
    }


def api_skills() -> dict:
    index = load_index()
    sandboxes = index.get("sandboxes") or {}
    rows = []
    for slug, meta in sandboxes.items():
        md = SKILLS / slug / "SKILL.md"
        fm: dict = {}
        if md.exists():
            fm = parse_frontmatter(md.read_text(encoding="utf-8"))
        rows.append(
            {
                "slug": slug,
                "name": meta.get("name") or fm.get("display_name") or slug,
                "description": meta.get("description") or fm.get("description") or "",
                "triggers": meta.get("triggers") or fm.get("triggers") or [],
                "tags": meta.get("tags") or fm.get("tags") or [],
                "tools": meta.get("tools") or fm.get("tools") or [],
                "session_count": int(meta.get("session_count") or fm.get("session_count") or 0),
                "last_active_date": meta.get("last_active_date") or fm.get("last_active_date") or "",
                "has_analysis_skill": (SKILLS / slug / "analysis-skill" / "SKILL.md").exists(),
                "has_references": bool(meta.get("has_references"))
                or (
                    (SKILLS / slug / "references").is_dir()
                    and any((SKILLS / slug / "references").glob("*.md"))
                ),
                "has_scripts": bool(meta.get("has_scripts"))
                or (
                    (SKILLS / slug / "scripts").is_dir()
                    and any((SKILLS / slug / "scripts").iterdir())
                ),
            }
        )
    rows.sort(key=lambda r: (-r["session_count"], r["name"]))
    return {"skills": rows}


def api_skill(slug: str) -> dict | None:
    safe = Path(slug).name
    md = SKILLS / safe / "SKILL.md"
    if not md.exists():
        return None
    text = md.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    body = _FRONTMATTER_RE.sub("", text, count=1)
    analysis_path = SKILLS / safe / "analysis-skill" / "SKILL.md"
    analysis = None
    if analysis_path.exists():
        atext = analysis_path.read_text(encoding="utf-8")
        analysis = {
            "frontmatter": parse_frontmatter(atext),
            "body": _FRONTMATTER_RE.sub("", atext, count=1).strip(),
        }
    refs_dir = SKILLS / safe / "references"
    refs = []
    if refs_dir.is_dir():
        for p in sorted(refs_dir.glob("*.md")):
            refs.append({"name": p.name, "body": p.read_text(encoding="utf-8")})
    scripts_dir = SKILLS / safe / "scripts"
    scripts = []
    if scripts_dir.is_dir():
        for p in sorted(scripts_dir.iterdir()):
            if p.is_file():
                scripts.append({"name": p.name, "body": p.read_text(encoding="utf-8", errors="replace")})
    return {
        "slug": safe,
        "frontmatter": fm,
        "body": body.strip(),
        "analysis": analysis,
        "references": refs,
        "scripts": scripts,
        "package": {
            "layout": [x.name for x in sorted((SKILLS / safe).iterdir()) if not x.name.startswith(".")],
            "router_hint": "Match request to description/triggers/tags in catalog.json, then load SKILL.md + references/ + scripts/.",
        },
    }


def api_classification(day: str) -> dict | None:
    path = LANGSMITH / "classification" / f"{Path(day).name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sessions = data.get("sessions") or {}
    by_slug: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    new_count = 0
    rows = []
    for sid, info in sessions.items():
        slug = str(info.get("slug") or "unknown")
        by_slug[slug] += 1
        source = str(info.get("source") or info.get("source_tool") or "langsmith")
        by_source[source] += 1
        if info.get("is_new"):
            new_count += 1
        rows.append(
            {
                "session_id": sid,
                "slug": slug,
                "name": info.get("name") or slug,
                "is_new": bool(info.get("is_new")),
                "source": source,
                "reasoning": info.get("reasoning") or "",
            }
        )
    rows.sort(key=lambda r: (r["slug"], r["session_id"]))
    return {
        "date": data.get("date") or day,
        "generated_at": data.get("generated_at"),
        "session_count": len(sessions),
        "new_sandbox_assignments": new_count,
        "by_slug": [{"slug": k, "count": v, "name": next((r["name"] for r in rows if r["slug"] == k), k)} for k, v in by_slug.most_common()],
        "by_source": [{"source": k, "count": v} for k, v in by_source.most_common()],
        "sessions": rows,
    }


def api_conversations(day_label: str | None, limit: int = 200) -> dict:
    dirs = conversation_dirs()
    if day_label:
        dirs = [(label, path) for label, path in dirs if label == day_label]
    rows = []
    for label, path in dirs:
        for md in sorted(path.glob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter(text)
            rows.append(
                {
                    "id": md.stem,
                    "label": label,
                    "path": str(md.relative_to(ROOT)).replace("\\", "/"),
                    "session_id": fm.get("session_id") or md.stem,
                    "source": fm.get("source") or ("local" if "/local/" in label or label.startswith("local/") else "langsmith"),
                    "source_tool": fm.get("source_tool") or "",
                    "project": fm.get("project") or "",
                    "date": fm.get("date") or "",
                    "turn_count": fm.get("turn_count") or 0,
                    "truncated": str(fm.get("truncated")).lower() == "true",
                }
            )
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return {"conversations": rows, "dirs": [label for label, _ in conversation_dirs()]}


def api_conversation_file(rel: str) -> dict | None:
    path = (ROOT / rel).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        return None
    if not path.is_file() or path.suffix != ".md":
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    body = _FRONTMATTER_RE.sub("", text, count=1)
    return {"path": rel, "frontmatter": fm, "body": body.strip()}


def api_capture(limit: int = 300) -> dict:
    if not CAPTURE.exists():
        return {"exists": False, "messages": [], "count": 0}
    raw = json.loads(CAPTURE.read_text(encoding="utf-8"))
    msgs = raw.get("messages") or []
    return {
        "exists": True,
        "path": str(CAPTURE.relative_to(ROOT)).replace("\\", "/"),
        "updatedAt": raw.get("updatedAt"),
        "count": len(msgs),
        "messages": msgs[-limit:],
        "byTool": dict(Counter(str(m.get("tool") or "unknown") for m in msgs)),
        "byDay": dict(Counter(str(m.get("day") or "?") for m in msgs)),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[ui] {self.address_string()} {fmt % args}")

    def _json(self, code: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/overview":
            return self._json(200, api_overview())
        if path == "/api/skills":
            return self._json(200, api_skills())
        if path.startswith("/api/skills/"):
            slug = unquote(path.removeprefix("/api/skills/").strip("/"))
            data = api_skill(slug)
            return self._json(200, data) if data else self._json(404, {"error": "not found"})
        if path.startswith("/api/classification/"):
            day = unquote(path.removeprefix("/api/classification/").strip("/"))
            data = api_classification(day)
            return self._json(200, data) if data else self._json(404, {"error": "not found"})
        if path == "/api/classification":
            dates = list_classification_dates()
            day = qs.get("date", [dates[0] if dates else ""])[0]
            data = api_classification(day) if day else {"sessions": [], "by_slug": []}
            return self._json(200, data)
        if path == "/api/conversations":
            label = qs.get("dir", [None])[0]
            limit = int(qs.get("limit", ["200"])[0])
            return self._json(200, api_conversations(label, limit=limit))
        if path == "/api/conversation":
            rel = qs.get("path", [""])[0]
            data = api_conversation_file(rel) if rel else None
            return self._json(200, data) if data else self._json(404, {"error": "not found"})
        if path == "/api/capture":
            return self._json(200, api_capture())

        if path == "/" or path == "":
            self.path = "/index.html"
        return super().do_GET()


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", _PORT), Handler)
    print(f"Proto2 analyzer -> http://127.0.0.1:{_PORT}")
    print(f"Reading data from {DATA}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
