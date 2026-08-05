"""Classify today's sessions into existing/new sandboxes, cheaply, before any per-sandbox analysis."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from analyze import call_openrouter, extract_json_object
from extract import get_tz
from skills import parse_frontmatter, skill_dir, slugify

SIGNATURE_SAMPLE_CHARS = 1200

CLASSIFY_SYSTEM_PROMPT = """You classify groups of agent sessions against a library of known
sandbox scenarios ("skills"), so future work on the same scenario reuses one cumulative skill instead of
fragmenting into near-duplicates.

Sessions may come from:
- SME-facing product sandboxes (often LangSmith; sample often starts with a SYSTEM prompt), or
- local coding-agent chats (Claude Code, Codex, OpenCode, Gemini; sample may be the opening USER turn).

You will receive:
- EXISTING SKILLS: a list of {slug, name, description, triggers, tags, tools} — the agent router uses
  description/triggers/tags to pick a skill for an incoming sandbox request. Prefer matching on those.
- GROUPS: a list of {group_key, sample, session_count, source_tool} - each group is one distinct scenario
  (sessions with an identical opening signature were already merged in code). "sample" is a text excerpt
  representative of that scenario. "source_tool" is langsmith|claude|codex|opencode|gemini|live|unknown.

For EACH group, decide either:
(a) it MATCHES an existing skill (same sandbox scenario, e.g. same product + same persona + same task), or
(b) it is a genuinely NEW sandbox scenario not covered by any existing skill

When proposing new_sandboxes, write description as third-person WHAT+WHEN with trigger terms, and include
triggers/tags arrays the skill router can use later.

Be conservative about proposing new sandboxes: only propose new when you are confident nothing existing fits.
Do not merge a coding-agent task into an unrelated SME product skill just because keywords overlap.
If multiple groups in this batch are the same new scenario, give them the SAME new_key so they collapse into
one proposal.

Respond with a single valid JSON object only (no markdown fences, no commentary):
{
  "decisions": [
    {
      "group_key": "<the group_key>",
      "matched_slug": "<existing slug>" or null,
      "new_key": "<short proposal key, e.g. 'medibuddy-dental'>" or null,
      "reasoning": "one sentence"
    }
  ],
  "new_sandboxes": {
    "<new_key>": {
      "name": "human-readable sandbox name",
      "description": "third-person WHAT + WHEN with trigger terms",
      "triggers": ["phrase1", "phrase2"],
      "tags": ["domain", "task"]
    }
  }
}

Rules:
- Every group MUST appear exactly once in "decisions".
- Exactly ONE of matched_slug/new_key must be non-null per decision, never both, never neither.
- Every new_key used in "decisions" MUST have a matching entry in "new_sandboxes".
"""


def session_signature(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())[:SIGNATURE_SAMPLE_CHARS]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


_SYSTEM_TURN_RE = re.compile(r"\[1\]\s*SYSTEM:\s*\n(.*?)(?=\n\[\d+\]\s*\w+:|\Z)", re.DOTALL)


_USER_TURN_RE = re.compile(r"\[\d+\]\s*USER:\s*\n(.*?)(?=\n\[\d+\]\s*\w+:|\Z)", re.DOTALL)


def build_session_digests(conv_dirs: Path | list[Path]) -> list[dict[str, Any]]:
    dirs = [conv_dirs] if isinstance(conv_dirs, Path) else list(conv_dirs)
    digests = []
    for conv_dir in dirs:
        for path in sorted(conv_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(text)
            transcript = re.sub(r"^---.*?---\n", "", text, count=1, flags=re.DOTALL)
            _, _, transcript = transcript.partition("## Transcript")
            transcript = transcript.strip()

            # Prefer SYSTEM turn (SME sandbox definition); else opening USER (coding agents).
            match = _SYSTEM_TURN_RE.search(transcript)
            if match:
                signature_source = match.group(1).strip()
            else:
                user_match = _USER_TURN_RE.search(transcript)
                signature_source = user_match.group(1).strip() if user_match else transcript

            source_tool = str(frontmatter.get("source_tool") or frontmatter.get("source") or "unknown")
            # Keep coding-agent vs SME groups from colliding on similar openers.
            signature = session_signature(f"{source_tool}\n{signature_source}")
            sample = transcript[:SIGNATURE_SAMPLE_CHARS]
            digests.append(
                {
                    "session_id": str(frontmatter.get("session_id") or path.stem),
                    "signature": signature,
                    "sample": sample,
                    "source_tool": source_tool,
                    "source": str(frontmatter.get("source") or source_tool),
                }
            )
    return digests


def group_digests(digests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for digest in digests:
        sig = digest["signature"]
        group = groups.setdefault(
            sig,
            {
                "sample": digest["sample"],
                "session_ids": [],
                "source_tool": digest.get("source_tool", "unknown"),
            },
        )
        group["session_ids"].append(digest["session_id"])
    return groups


def load_existing_skill_headers(skills_root: Path) -> list[dict[str, Any]]:
    if not skills_root.exists():
        return []
    headers = []
    for directory in sorted(skills_root.iterdir()):
        md_path = directory / "SKILL.md"
        if not md_path.exists():
            continue
        frontmatter = parse_frontmatter(md_path.read_text(encoding="utf-8"))
        headers.append(
            {
                "slug": str(frontmatter.get("slug") or directory.name),
                "name": str(frontmatter.get("display_name") or frontmatter.get("name") or directory.name),
                "description": str(frontmatter.get("description") or ""),
                "triggers": list(frontmatter.get("triggers") or []),
                "tags": list(frontmatter.get("tags") or []),
                "tools": list(frontmatter.get("tools") or []),
            }
        )
    return headers


def classify_day_with_llm(
    groups: dict[str, dict[str, Any]],
    existing_skills: list[dict[str, Any]],
    *,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    group_payload = [
        {
            "group_key": key,
            "sample": group["sample"],
            "session_count": len(group["session_ids"]),
            "source_tool": group.get("source_tool", "unknown"),
        }
        for key, group in groups.items()
    ]
    user_prompt = (
        f"EXISTING SKILLS:\n{json.dumps(existing_skills, ensure_ascii=False, indent=2)}\n\n"
        f"GROUPS:\n{json.dumps(group_payload, ensure_ascii=False, indent=2)}"
    )
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    last_error: Exception | None = None
    raw = ""
    for attempt in range(1, 3):
        try:
            raw = call_openrouter(messages, model=model, api_key=api_key)
            data = extract_json_object(raw)
            _validate_classification(data, set(groups))
            return data
        except Exception as exc:  # noqa: BLE001 — LLM-only, retry once with correction
            last_error = exc
            if attempt >= 2:
                break
            messages = [
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw or ""},
                {"role": "user", "content": f"Invalid response: {exc}. Return ONLY the corrected JSON object."},
            ]
    raise RuntimeError(f"LLM classification failed after retries: {last_error}")


def _validate_classification(data: dict[str, Any], group_keys: set[str]) -> None:
    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("'decisions' must be a list")
    seen = set()
    new_sandboxes = data.get("new_sandboxes") or {}
    for decision in decisions:
        key = decision.get("group_key")
        if key not in group_keys:
            raise ValueError(f"unknown group_key: {key}")
        seen.add(key)
        matched, new_key = decision.get("matched_slug"), decision.get("new_key")
        if bool(matched) == bool(new_key):
            raise ValueError(f"group {key}: exactly one of matched_slug/new_key required")
        if new_key and new_key not in new_sandboxes:
            raise ValueError(f"new_key {new_key} not defined in new_sandboxes")
    missing = group_keys - seen
    if missing:
        raise ValueError(f"groups missing decisions: {missing}")


def write_classification_audit(
    day: date,
    session_decisions: dict[str, dict[str, Any]],
    output_root: Path,
) -> Path:
    out_dir = output_root / "classification"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{day.isoformat()}.json"
    out_path.write_text(
        json.dumps(
            {"date": day.isoformat(), "generated_at": datetime.now(get_tz()).isoformat(), "sessions": session_decisions},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def classify_today(
    *,
    conv_dirs: Path | list[Path],
    skills_root: Path,
    output_root: Path,
    day: date,
    model: str,
    api_key: str,
) -> dict[str, dict[str, Any]]:
    digests = build_session_digests(conv_dirs)
    groups = group_digests(digests)
    existing_skills = load_existing_skill_headers(skills_root)
    digest_by_id = {d["session_id"]: d for d in digests}

    print(f"Classifying {len(digests)} session(s) -> {len(groups)} distinct group(s)...")
    classification = classify_day_with_llm(groups, existing_skills, model=model, api_key=api_key)

    existing_by_slug = {s["slug"]: s for s in existing_skills}
    new_sandboxes = classification.get("new_sandboxes") or {}
    used_slugs = set(existing_by_slug)
    new_key_to_slug: dict[str, str] = {}
    for new_key, info in new_sandboxes.items():
        base = slugify(str(info.get("name") or new_key))
        candidate = base
        n = 2
        while candidate in used_slugs or skill_dir(skills_root, candidate).exists():
            candidate = f"{base}-{n}"
            n += 1
        used_slugs.add(candidate)
        new_key_to_slug[new_key] = candidate

    session_decisions: dict[str, dict[str, Any]] = {}
    for decision in classification["decisions"]:
        group_key = decision["group_key"]
        session_ids = groups[group_key]["session_ids"]
        if decision.get("matched_slug"):
            slug = decision["matched_slug"]
            if slug not in existing_by_slug:
                raise ValueError(f"matched_slug not in existing skills: {slug}")
            name = existing_by_slug[slug]["name"]
            description = existing_by_slug[slug]["description"]
            is_new = False
        else:
            new_key = decision["new_key"]
            slug = new_key_to_slug[new_key]
            info = new_sandboxes[new_key]
            name = str(info.get("name") or new_key)
            description = str(info.get("description") or "")
            is_new = True
        for session_id in session_ids:
            meta = digest_by_id.get(session_id, {})
            session_decisions[session_id] = {
                "slug": slug,
                "name": name,
                "description": description,
                "is_new": is_new,
                "reasoning": decision.get("reasoning", ""),
                "source": meta.get("source", "unknown"),
                "source_tool": meta.get("source_tool", "unknown"),
            }

    write_classification_audit(day, session_decisions, output_root)
    print(f"Classification done: {len(session_decisions)} session(s) -> {len(used_slugs)} sandbox(es)")
    return session_decisions
