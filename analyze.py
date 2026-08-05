"""Build next-day reinforcement feedback MD from today's conversation MDs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

# Override via ANALYSIS_MODEL in .env
DEFAULT_MODEL = "anthropic/claude-sonnet-5-20260630"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JSON_RETRY_ATTEMPTS = 2
MAX_BUNDLE_CHARS = 900_000

FEEDBACK_SYSTEM_PROMPT = """You are the reinforcement / continuous-improvement brain for an AI agent.

You will receive ALL SME–agent conversations from ONE calendar day (already extracted as markdown).
Your job is to produce a single reinforcement-feedback document that the SAME agent will read
BEFORE its next day of work, so it can:
- reduce user/SME hassle
- stop making the same mistakes
- stop forcing users to "tell the agent separately" things it should already know
- improve UX, grounding, and usefulness

Think like RLHF / online preference learning distilled into clear operational rules.

You MUST respond with a single valid JSON object only (no markdown fences, no commentary):
{
  "title": "short title for tomorrow's feedback pack",
  "executive_summary": "2-4 sentences: what went wrong/right today and the priority fix",
  "mistakes": [
    {
      "mistake": "what went wrong",
      "why_it_hurts_ux": "user/SME impact",
      "evidence": "short quote or session reference",
      "do_instead": "concrete next-time behavior"
    }
  ],
  "user_hassle_hotspots": [
    "places users had to over-explain, repeat, or compensate for the agent"
  ],
  "knowledge_to_internalize": [
    "facts, domain rules, tools, or context the agent should already have next time"
  ],
  "behavior_rules_for_next_run": [
    "imperative rules the agent must follow tomorrow (short, enforceable)"
  ],
  "prompt_additions": [
    "exact sentences/snippets worth adding to the system prompt"
  ],
  "prioritized_actions": [
    "ordered list: highest-leverage improvements first"
  ],
  "positive_patterns_to_keep": [
    "what worked today and should be preserved"
  ]
}

Rules:
- Be specific and evidence-based. Prefer actionable rules over vague advice.
- Optimize for LESS user hassle and BETTER UX next time.
- If transcripts are thin/empty/failed, say so and still give defensive next-day rules.
- Do not invent tools or policies that are not implied by the conversations.
"""


def call_openrouter(messages: list[dict[str, str]], *, model: str, api_key: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/proto2",
        "X-Title": "Proto2 Daily Reinforcement Feedback",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:1000]}")
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response: {json.dumps(data)[:1000]}") from exc


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Model JSON was not an object")
    return data


def analyze_day_with_llm(
    bundle: str, *, model: str, api_key: str, system_prompt: str = FEEDBACK_SYSTEM_PROMPT
) -> dict[str, Any]:
    user_prompt = (
        "Analyze ALL of today's SME–agent conversation markdown files below.\n"
        "Produce the reinforcement JSON that the agent must follow on the NEXT day "
        "to minimize user hassle and improve UX.\n\n"
        f"TODAY'S CONVERSATIONS:\n{bundle}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_error: Exception | None = None
    raw = ""
    for attempt in range(1, JSON_RETRY_ATTEMPTS + 1):
        try:
            raw = call_openrouter(messages, model=model, api_key=api_key)
            return extract_json_object(raw)
        except Exception as exc:  # noqa: BLE001 — LLM-only, no heuristic fallback
            last_error = exc
            if attempt >= JSON_RETRY_ATTEMPTS:
                break
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw or ""},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON for the required schema. "
                        f"Parse error: {exc}. Return ONLY the corrected JSON object."
                    ),
                },
            ]
    raise RuntimeError(f"LLM feedback analysis failed after retries: {last_error}")


def load_conversation_bundle(conv_dir: Path | list[Path]) -> tuple[str, int, bool]:
    dirs = [conv_dir] if isinstance(conv_dir, Path) else list(conv_dir)
    files: list[Path] = []
    for d in dirs:
        files.extend(sorted(d.glob("*.md")))
    if not files:
        raise FileNotFoundError(f"No conversation markdown files in {dirs}")
    return _bundle_files(files)


def load_conversation_bundle_for_sessions(
    conv_dirs: Path | list[Path], session_ids: list[str]
) -> tuple[str, int, bool]:
    from extract import safe_filename

    dirs = [conv_dirs] if isinstance(conv_dirs, Path) else list(conv_dirs)
    files: list[Path] = []
    for sid in session_ids:
        name = f"{safe_filename(sid)}.md"
        for d in dirs:
            candidate = d / name
            if candidate.exists():
                files.append(candidate)
                break
    if not files:
        raise FileNotFoundError(f"No conversation markdown files for given session_ids in {dirs}")
    return _bundle_files(files)


def _bundle_files(files: list[Path]) -> tuple[str, int, bool]:
    parts: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        parts.append(f"\n\n===== FILE: {path.name} =====\n{text}")
    bundle = "".join(parts)
    truncated = False
    if len(bundle) > MAX_BUNDLE_CHARS:
        bundle = bundle[:MAX_BUNDLE_CHARS] + "\n\n[TRUNCATED: daily conversation bundle exceeded limit]"
        truncated = True
    return bundle, len(files), truncated
