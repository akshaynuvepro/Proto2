"""Self-contained OpenRouter (OpenAI-compatible) text client for skill authoring.

Only used by the skill generator. Reads credentials from the environment or a
``secrets.env`` file. Returns Markdown text (not JSON) because a SKILL.md is a
document, not a structured payload.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: str | Path) -> None:
    """Load simple KEY=VALUE lines into os.environ (does not overwrite existing)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class ModelSettings:
    model: str
    api_key: str
    provider: str = "openai"               # openai | anthropic
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 180.0
    max_retries: int = 2
    temperature: float = 0.2
    max_tokens: int = 8192

    @classmethod
    def from_env(cls) -> "ModelSettings":
        # accept the key under any of these names
        key = (
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        ).strip()
        if not key:
            raise RuntimeError("no model API key set (OPENROUTER_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY)")

        configured_model = os.getenv("ASSESSMENT_FACTORY_MODEL", os.getenv("ASSESSMENT_EVOLUTION_MODEL", "")).strip()
        base_url = os.getenv("OPENROUTER_BASE_URL", "").strip().rstrip("/")

        # detect provider
        if key.startswith("sk-ant-") or "anthropic.com" in base_url or os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
            base_url = base_url or "https://api.anthropic.com"
            model = configured_model or "claude-sonnet-4-5-20250929"
            # a native Anthropic model id has no provider prefix
            if "/" in model:
                model = model.split("/", 1)[1]
        else:
            provider = "openai"
            base_url = base_url or "https://openrouter.ai/api/v1"
            model = configured_model or "openai/gpt-4.1-mini"

        return cls(
            model=model,
            api_key=key,
            provider=provider,
            base_url=base_url,
            timeout_seconds=float(os.getenv("ASSESSMENT_MODEL_TIMEOUT", "180")),
            max_retries=int(os.getenv("ASSESSMENT_MODEL_RETRIES", "2")),
            temperature=float(os.getenv("ASSESSMENT_MODEL_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("ASSESSMENT_FACTORY_MAX_TOKENS", "8192")),
        )


def _post(client, url, headers, payload):
    r = client.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()


def generate_text(settings: ModelSettings, *, system: str, user: str) -> tuple[str, dict]:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("httpx is required for model-backed skill generation") from exc

    import time
    last_error: Exception | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            with httpx.Client(timeout=settings.timeout_seconds) as client:
                if settings.provider == "anthropic":
                    body = _post(
                        client,
                        f"{settings.base_url}/v1/messages",
                        {
                            "x-api-key": settings.api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        {
                            "model": settings.model,
                            "max_tokens": settings.max_tokens,
                            "temperature": settings.temperature,
                            "system": system,
                            "messages": [{"role": "user", "content": user}],
                        },
                    )
                    parts = body.get("content") or []
                    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
                    usage = body.get("usage") or {}
                    return text, {"provider": "anthropic", "model": settings.model,
                                  "attempt": attempt, "usage": usage}
                else:
                    body = _post(
                        client,
                        f"{settings.base_url}/chat/completions",
                        {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
                        {
                            "model": settings.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "temperature": settings.temperature,
                            "max_tokens": settings.max_tokens,
                        },
                    )
                    text = body["choices"][0]["message"]["content"]
                    usage = body.get("usage") or {}
                    return text, {"provider": "openai", "model": settings.model,
                                  "attempt": attempt, "usage": usage}
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= settings.max_retries:
                break
            time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(f"model generation failed after {settings.max_retries + 1} attempts: {last_error}") from last_error


def strip_code_fence(text: str) -> str:
    """If the model wrapped the whole doc in a ```markdown fence, unwrap it."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip() + "\n"
