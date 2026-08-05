#!/usr/bin/env python3
"""Rebuild data/skills/catalog.json + enrich index.json from existing SKILL.md frontmatter."""

from __future__ import annotations

from pathlib import Path

from extract import ROOT
from skills import load_index, read_references, read_scripts, read_skill_body, write_catalog


def main() -> int:
    skills_root = ROOT / "data" / "skills"
    index = load_index(skills_root)
    sandboxes = index.setdefault("sandboxes", {})

    for directory in sorted(skills_root.iterdir()):
        if not directory.is_dir():
            continue
        parsed = read_skill_body(directory / "SKILL.md")
        if parsed is None:
            continue
        fm, _ = parsed
        slug = str(fm.get("slug") or directory.name)
        entry = sandboxes.setdefault(slug, {"name": slug, "session_count": 0, "last_active_date": ""})
        entry["name"] = str(fm.get("display_name") or fm.get("name") or entry.get("name") or slug)
        entry["description"] = str(fm.get("description") or entry.get("description") or "")
        entry["triggers"] = list(fm.get("triggers") or entry.get("triggers") or [])
        entry["tags"] = list(fm.get("tags") or entry.get("tags") or [])
        entry["tools"] = list(fm.get("tools") or entry.get("tools") or [])
        if fm.get("session_count") is not None:
            entry["session_count"] = int(fm["session_count"])
        if fm.get("last_active_date"):
            entry["last_active_date"] = str(fm["last_active_date"])
        entry["has_references"] = bool(read_references(skills_root, slug))
        entry["has_scripts"] = bool(read_scripts(skills_root, slug))

    skills_root.mkdir(parents=True, exist_ok=True)
    (skills_root / "index.json").write_text(
        __import__("json").dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    catalog_path = write_catalog(skills_root)
    import json

    n = len(json.loads(catalog_path.read_text(encoding="utf-8"))["skills"])
    print(f"Updated {skills_root / 'index.json'}")
    print(f"Wrote {catalog_path} ({n} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
