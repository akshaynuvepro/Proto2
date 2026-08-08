"""Provider-neutral structured generation using an OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from .observability import Observability
from .prompts import Prompt


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ModelSettings:
    model: str
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 120.0
    max_retries: int = 2
    temperature: float = 0.1
    max_tokens: int = 8192

    @classmethod
    def from_env(cls) -> "ModelSettings":
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is required for model-backed stages")
        return cls(
            model=os.getenv("ASSESSMENT_EVOLUTION_MODEL", os.getenv("ANALYSIS_MODEL", "openai/gpt-4.1-mini")),
            api_key=key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            timeout_seconds=float(os.getenv("ASSESSMENT_MODEL_TIMEOUT", "120")),
            max_retries=int(os.getenv("ASSESSMENT_MODEL_RETRIES", "2")),
            temperature=float(os.getenv("ASSESSMENT_MODEL_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("ASSESSMENT_MODEL_MAX_TOKENS", "8192")),
        )


class StructuredModelClient:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        observability: Observability | None = None,
    ) -> None:
        self.settings = settings
        self.observability = observability

    def generate_json(
        self,
        *,
        prompt: Prompt,
        user_payload: dict[str, Any],
        observation_name: str,
        parent_artifact_ids: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for model-backed stages") from exc
        messages = [
            {"role": "system", "content": prompt.text},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
            },
        ]
        request = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "response_format": {"type": "json_object"},
        }
        metadata = {
            "prompt_name": prompt.name,
            "prompt_git_hash": prompt.git_hash,
            "parent_artifact_ids": parent_artifact_ids or [],
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                context = (
                    self.observability.generation(
                        observation_name,
                        model=self.settings.model,
                        input=messages,
                        metadata={**metadata, "retry": attempt},
                        model_parameters={
                            "temperature": self.settings.temperature,
                            "max_tokens": self.settings.max_tokens,
                        },
                    )
                    if self.observability
                    else _null_context()
                )
                with context as generation:
                    with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                        response = client.post(
                            f"{self.settings.base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.settings.api_key}",
                                "Content-Type": "application/json",
                            },
                            json=request,
                        )
                    response.raise_for_status()
                    body = response.json()
                    text = body["choices"][0]["message"]["content"]
                    parsed = _parse_json_object(text)
                    usage = body.get("usage") or {}
                    if generation is not None:
                        generation.update(
                            output=parsed,
                            usage_details={
                                "input": usage.get("prompt_tokens", 0),
                                "output": usage.get("completion_tokens", 0),
                                "total": usage.get("total_tokens", 0),
                            },
                        )
                    return parsed, {
                        "provider": "openrouter",
                        "model": self.settings.model,
                        "prompt": prompt.name,
                        "prompt_git_hash": prompt.git_hash,
                        "attempt": attempt,
                        "usage": usage,
                    }
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(min(2**attempt, 4))
        raise RuntimeError(
            f"structured generation failed after {self.settings.max_retries + 1} attempts"
        ) from last_error


def _parse_json_object(text: str) -> dict[str, Any]:
    match = _FENCE.match(text)
    if match:
        text = match.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model response must be one JSON object")
    return parsed


class _null_context:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: Any) -> None:
        return None
