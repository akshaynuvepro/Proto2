"""Minimal OpenRouter tool-calling agent loop (no LangChain)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from openrouter import OpenRouterSettings, chat_message, strip_code_fence

Handler = Callable[[dict[str, Any]], Any]


@dataclass
class AgentResult:
    text: str
    meta: dict[str, Any]
    trace: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


def _safe_args(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_raw": parsed}
    except json.JSONDecodeError:
        return {"_parse_error": raw[:500]}


def _dispatch(
    name: str,
    args: dict[str, Any],
    handlers: dict[str, Handler],
) -> tuple[str, bool]:
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool: {name}"}), False
    try:
        out = fn(args)
        if isinstance(out, str):
            return out, True
        return json.dumps(out, ensure_ascii=False, default=str), True
    except Exception as exc:  # noqa: BLE001 — surface to model, keep loop alive
        return json.dumps({"error": str(exc)}), False


def _merge_usage(acc: dict[str, int], usage: dict[str, Any] | None) -> None:
    for k, v in (usage or {}).items():
        if isinstance(v, int):
            acc[k] = acc.get(k, 0) + v


def _needs_json(response_format: dict[str, Any] | None, text: str) -> bool:
    if not response_format or response_format.get("type") != "json_object":
        return False
    try:
        json.loads(strip_code_fence(text))
        return False
    except (json.JSONDecodeError, TypeError):
        return True


def run_agent(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    handlers: dict[str, Handler],
    settings: OpenRouterSettings | None = None,
    max_rounds: int = 10,
    max_tokens: int | None = 8192,
    response_format: dict[str, Any] | None = None,
    temperature: float | None = None,
) -> AgentResult:
    """Run chat with tools until the model stops calling tools or max_rounds hit."""
    msgs = list(messages)
    trace: list[dict[str, Any]] = []
    usage_acc: dict[str, int] = {}
    last_meta: dict[str, Any] = {}
    final_text = ""
    rounds = 0

    for _ in range(max_rounds):
        message, meta = chat_message(
            msgs,
            settings=settings,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        last_meta = meta
        _merge_usage(usage_acc, meta.get("usage"))
        msgs.append(message)
        rounds += 1

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = message.get("content") or ""
            final_text = content if isinstance(content, str) else str(content)
            break

        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            name = str(fn.get("name") or "")
            args = _safe_args(fn.get("arguments"))
            result, ok = _dispatch(name, args, handlers)
            trace.append({"tool": name, "ok": ok})
            if len(result) > 24_000:
                result = result[:24_000] + "\n...[truncated]"
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": result,
                }
            )

    if not final_text or _needs_json(response_format, final_text):
        msgs.append(
            {
                "role": "user",
                "content": (
                    "Produce your final answer now without calling tools."
                    + (" Return ONLY valid JSON matching the required schema." if response_format else "")
                ),
            }
        )
        message, meta = chat_message(
            msgs,
            settings=settings,
            tools=None,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        last_meta = meta
        _merge_usage(usage_acc, meta.get("usage"))
        content = message.get("content") or ""
        final_text = content if isinstance(content, str) else str(content)
        rounds += 1

    return AgentResult(
        text=final_text,
        meta={**last_meta, "usage": usage_acc or last_meta.get("usage") or {}},
        trace=trace,
        rounds=rounds,
    )
