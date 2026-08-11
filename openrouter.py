"""OpenRouter LLM client — sole model provider for Skill Lab."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_REFERER = "https://localhost/skill-lab"
DEFAULT_TITLE = "Skill Lab"


@dataclass(frozen=True, slots=True)
class OpenRouterSettings:
    api_key: str
    model: str = DEFAULT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 300.0
    max_retries: int = 2
    temperature: float = 0.1
    max_tokens: int = 8192
    referer: str = DEFAULT_REFERER
    title: str = DEFAULT_TITLE

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def embeddings_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/embeddings"

    @classmethod
    def from_env(cls, *, require_key: bool = True) -> "OpenRouterSettings":
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if require_key and not key:
            raise RuntimeError("OPENROUTER_API_KEY is required.")
        return cls(
            api_key=key,
            model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            embedding_model=os.getenv("OPENROUTER_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
            or DEFAULT_EMBEDDING_MODEL,
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
            or DEFAULT_BASE_URL,
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT", "300")),
            max_retries=int(os.getenv("OPENROUTER_RETRIES", "2")),
            temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "8192")),
            referer=os.getenv("OPENROUTER_HTTP_REFERER", DEFAULT_REFERER),
            title=os.getenv("OPENROUTER_APP_TITLE", DEFAULT_TITLE),
        )


def load_dotenv(path: Path | None = None) -> None:
    candidate = path or Path(__file__).resolve().parent / ".env"
    if not candidate.exists():
        return
    for line in candidate.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Prefer project .env over a stale process env (common in IDE shells).
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def chat_message(
    messages: list[dict[str, Any]],
    *,
    settings: OpenRouterSettings | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """OpenAI-compatible chat; returns the assistant message dict (may include tool_calls)."""
    cfg = settings or OpenRouterSettings.from_env(require_key=False)
    key = (cfg.api_key or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    use_model = (model or cfg.model or DEFAULT_MODEL).strip()
    payload: dict[str, Any] = {
        "model": use_model,
        "messages": messages,
        "temperature": cfg.temperature if temperature is None else temperature,
    }
    tokens = cfg.max_tokens if max_tokens is None else max_tokens
    if tokens:
        payload["max_tokens"] = tokens
    if response_format is not None:
        payload["response_format"] = response_format
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": cfg.referer,
        "X-Title": cfg.title,
    }
    timeout = timeout_seconds if timeout_seconds is not None else cfg.timeout_seconds
    last_err: Exception | None = None
    data: dict[str, Any] = {}
    for attempt in range(cfg.max_retries + 1):
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(30.0, timeout))) as client:
                resp = client.post(cfg.chat_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:1000]}")
                data = resp.json()
            break
        except Exception as exc:  # noqa: BLE001 — retry then raise
            last_err = exc
            if attempt >= cfg.max_retries:
                raise
    else:
        raise last_err or RuntimeError("OpenRouter call failed")

    try:
        message = data["choices"][0]["message"]
        if not isinstance(message, dict):
            raise TypeError("message is not a dict")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response: {json.dumps(data)[:1000]}") from exc
    usage = data.get("usage") or {}
    return message, {
        "provider": "openrouter",
        "model": use_model,
        "usage": usage,
        "base_url": cfg.base_url,
    }


def chat_completions(
    messages: list[dict[str, Any]],
    *,
    settings: OpenRouterSettings | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, dict[str, Any]]:
    message, meta = chat_message(
        messages,
        settings=settings,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        tools=tools,
        tool_choice=tool_choice,
        timeout_seconds=timeout_seconds,
    )
    text = message.get("content") or ""
    if not isinstance(text, str):
        text = str(text)
    return text, meta


def embeddings(
    texts: list[str],
    *,
    settings: OpenRouterSettings | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> tuple[list[list[float]], dict[str, Any]]:
    """OpenAI-compatible embeddings via OpenRouter POST /embeddings."""
    cfg = settings or OpenRouterSettings.from_env(require_key=False)
    key = (cfg.api_key or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    use_model = (model or cfg.embedding_model or DEFAULT_EMBEDDING_MODEL).strip()
    payload: dict[str, Any] = {"model": use_model, "input": texts}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": cfg.referer,
        "X-Title": cfg.title,
    }
    timeout = timeout_seconds if timeout_seconds is not None else cfg.timeout_seconds
    last_err: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(30.0, timeout))) as client:
                resp = client.post(cfg.embeddings_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:1000]}")
                data = resp.json()
            break
        except Exception as exc:  # noqa: BLE001 — retry then raise
            last_err = exc
            if attempt >= cfg.max_retries:
                raise
    else:
        raise last_err or RuntimeError("OpenRouter embeddings call failed")

    try:
        rows = sorted(data["data"], key=lambda r: int(r["index"]))
        vectors = [list(r["embedding"]) for r in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter embeddings response: {json.dumps(data)[:1000]}") from exc
    if len(vectors) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
    usage = data.get("usage") or {}
    return vectors, {
        "provider": "openrouter",
        "model": use_model,
        "usage": usage,
        "base_url": cfg.base_url,
    }


def strip_code_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
