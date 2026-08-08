"""Optional Langfuse v4 tracing with local fail-open telemetry events."""

from __future__ import annotations

import json
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .privacy import telemetry_safe
from .schemas import canonical_json, utc_now


class Observability:
    def __init__(
        self,
        *,
        run_id: str,
        queue_path: Path | None = None,
        required: bool = False,
    ) -> None:
        self.run_id = run_id
        self.queue_path = queue_path
        self.required = required
        self.client: Any = None
        self.degraded_reason: str | None = None
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse import get_client

                self.client = get_client()
            except Exception as exc:  # telemetry must not corrupt local work
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                if required:
                    raise RuntimeError("Langfuse initialization failed") from exc

    def _local_event(self, payload: dict[str, Any]) -> None:
        if self.queue_path is None:
            return
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"recorded_at": utc_now(), "run_id": self.run_id, **payload}
        with self.queue_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event) + "\n")

    @contextmanager
    def span(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        input: Any = None,
    ) -> Iterator[Any]:
        safe_metadata = {"run_id": self.run_id, **(metadata or {})}
        if input is not None and not telemetry_safe(input):
            self._local_event(
                {
                    "event": "telemetry.suppressed",
                    "observation": name,
                    "reason": "content_policy",
                }
            )
            yield None
            return
        if self.client is None:
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "metadata": safe_metadata,
                }
            )
            yield None
            return
        try:
            context = self.client.start_as_current_observation(
                as_type="span",
                name=name,
                input=input,
                metadata=safe_metadata,
            )
        except Exception as exc:
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "metadata": safe_metadata,
                    "error": self.degraded_reason,
                }
            )
            if self.required:
                raise
            yield None
            return
        try:
            observation = context.__enter__()
        except Exception as exc:
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "metadata": safe_metadata,
                    "error": self.degraded_reason,
                }
            )
            if self.required:
                raise
            yield None
            return
        try:
            yield observation
        except BaseException as exc:
            context.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            try:
                context.__exit__(None, None, None)
            except Exception as exc:
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                self._local_event(
                    {
                        "event": "telemetry.pending",
                        "observation": name,
                        "metadata": safe_metadata,
                        "error": self.degraded_reason,
                    }
                )
                if self.required:
                    raise

    @contextmanager
    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any,
        metadata: dict[str, Any] | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        safe_metadata = {"run_id": self.run_id, **(metadata or {})}
        if not telemetry_safe(input):
            self._local_event(
                {
                    "event": "telemetry.suppressed",
                    "observation": name,
                    "reason": "content_policy",
                }
            )
            yield None
            return
        if self.client is None:
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "model": model,
                    "metadata": safe_metadata,
                }
            )
            yield None
            return
        try:
            context = self.client.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                input=input,
                metadata=safe_metadata,
                model_parameters=model_parameters or {},
            )
        except Exception as exc:
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "model": model,
                    "metadata": safe_metadata,
                    "error": self.degraded_reason,
                }
            )
            if self.required:
                raise
            yield None
            return
        try:
            observation = context.__enter__()
        except Exception as exc:
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            self._local_event(
                {
                    "event": "telemetry.pending",
                    "observation": name,
                    "model": model,
                    "metadata": safe_metadata,
                    "error": self.degraded_reason,
                }
            )
            if self.required:
                raise
            yield None
            return
        try:
            yield observation
        except BaseException as exc:
            context.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            try:
                context.__exit__(None, None, None)
            except Exception as exc:
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                self._local_event(
                    {
                        "event": "telemetry.pending",
                        "observation": name,
                        "model": model,
                        "metadata": safe_metadata,
                        "error": self.degraded_reason,
                    }
                )
                if self.required:
                    raise

    def score(
        self,
        *,
        name: str,
        value: float | bool | str,
        trace_id: str | None = None,
        observation_id: str | None = None,
        comment: str | None = None,
    ) -> None:
        payload = {
            "event": "telemetry.score",
            "name": name,
            "value": value,
            "trace_id": trace_id,
            "observation_id": observation_id,
            "comment": comment,
        }
        if self.client is None:
            self._local_event(payload)
            return
        try:
            create_score = getattr(self.client, "create_score", None)
            if create_score:
                create_score(
                    name=name,
                    value=value,
                    trace_id=trace_id,
                    observation_id=observation_id,
                    comment=comment,
                )
            else:
                self._local_event({**payload, "event": "telemetry.pending"})
        except Exception as exc:
            self._local_event(
                {
                    **payload,
                    "event": "telemetry.pending",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if self.required:
                raise

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception as exc:
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                self._local_event(
                    {"event": "telemetry.flush_failed", "error": self.degraded_reason}
                )
                if self.required:
                    raise

    def pending_events(self) -> list[dict[str, Any]]:
        if self.queue_path is None or not self.queue_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.queue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def backfill(self) -> dict[str, int]:
        if self.client is None:
            raise RuntimeError("Langfuse is not configured; pending telemetry cannot be backfilled")
        events = self.pending_events()
        receipt_path = (
            self.queue_path.with_name("telemetry.backfilled.jsonl")
            if self.queue_path
            else None
        )
        completed: set[str] = set()
        if receipt_path and receipt_path.exists():
            completed = {
                json.loads(line)["event_hash"]
                for line in receipt_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        sent = 0
        skipped = 0
        for event in events:
            event_hash = hashlib.sha256(
                json.dumps(event, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if event_hash in completed:
                skipped += 1
                continue
            name = str(event.get("observation") or event.get("name") or "telemetry.backfill")
            metadata = {
                "run_id": self.run_id,
                "backfilled": True,
                "original_event": event.get("event"),
                **dict(event.get("metadata") or {}),
            }
            with self.client.start_as_current_observation(
                as_type="span", name=name, metadata=metadata
            ) as observation:
                observation.update(output={"backfilled": True, "event_hash": event_hash})
            if receipt_path:
                with receipt_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(
                        canonical_json(
                            {
                                "event_hash": event_hash,
                                "backfilled_at": utc_now(),
                                "run_id": self.run_id,
                            }
                        )
                        + "\n"
                    )
            completed.add(event_hash)
            sent += 1
        self.flush()
        return {"sent": sent, "skipped": skipped, "pending": len(events)}

    def sync_prompts(self, prompts: list[Any], *, label: str | None = None) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("Langfuse is not configured; prompts cannot be mirrored")
        results = []
        for prompt in prompts:
            existing = None
            try:
                existing = self.client.get_prompt(prompt.name, label=label) if label else self.client.get_prompt(prompt.name)
            except Exception:
                existing = None
            existing_hash = (
                getattr(existing, "config", {}).get("git_hash")
                if existing is not None and isinstance(getattr(existing, "config", {}), dict)
                else None
            )
            if existing_hash == prompt.git_hash:
                results.append(
                    {
                        "name": prompt.name,
                        "git_hash": prompt.git_hash,
                        "status": "unchanged",
                        "langfuse_version": getattr(existing, "version", None),
                    }
                )
                continue
            created = self.client.create_prompt(
                name=prompt.name,
                prompt=prompt.text,
                labels=[label] if label else [],
                type="text",
                config={"git_hash": prompt.git_hash, "source": "git"},
                commit_message=f"Mirror Git prompt {prompt.git_hash}",
            )
            results.append(
                {
                    "name": prompt.name,
                    "git_hash": prompt.git_hash,
                    "status": "created",
                    "langfuse_version": getattr(created, "version", None),
                }
            )
        self.flush()
        return results
