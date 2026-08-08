"""Immutable filesystem artifact store with hash and lineage manifests."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import ArtifactManifest, SchemaError, canonical_json, content_hash, stable_id, utc_now


STAGE_DIRS = {
    "input": "00-input",
    "normalized": "01-normalized",
    "sanitized": "02-sanitized",
    "evidence_candidates": "03-evidence-candidates",
    "approved_evidence": "04-approved-evidence",
    "principle_candidates": "05-principle-candidates",
    "principle_bank": "06-principle-bank",
    "compiled_skill": "07-compiled-skill",
    "skillopt": "08-skillopt",
    "evaluation": "09-evaluation",
    "release": "10-release",
}


class ArtifactConflictError(RuntimeError):
    """An immutable path already exists with different content."""


def new_run_id(purpose: str = "assessment-evolution") -> str:
    return stable_id("run", {"purpose": purpose, "created_at": utc_now()})


@dataclass(slots=True)
class ArtifactStore:
    root: Path
    run_id: str
    purpose: str = "assessment-evolution"

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / ".staging").mkdir(exist_ok=True)
        for directory in STAGE_DIRS.values():
            (self.run_dir / directory).mkdir(exist_ok=True)
        if not self.events_path.exists():
            self._append_event(
                {
                    "event": "run.created",
                    "run_id": self.run_id,
                    "purpose": self.purpose,
                    "created_at": utc_now(),
                }
            )

    @property
    def run_dir(self) -> Path:
        return self.root / "runs" / self.run_id

    @property
    def events_path(self) -> Path:
        return self.run_dir / "manifest.events.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.run_dir / "manifest.json"

    def _safe_relative(self, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ValueError("artifact path must be relative and cannot traverse")
        resolved = (self.run_dir / raw).resolve()
        try:
            resolved.relative_to(self.run_dir)
        except ValueError as exc:
            raise ValueError("artifact path escapes run directory") from exc
        return resolved

    def _append_event(self, event: dict[str, Any]) -> None:
        # Each append is one write while the process-local lock prevents threads
        # interleaving records. Cross-process artifact conflicts remain hash-safe.
        lock = _event_lock(self.events_path)
        payload = canonical_json(event) + "\n"
        with lock, _filesystem_lock(self.run_dir / ".manifest.lock"):
            with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

    def put_bytes(
        self,
        *,
        stage: str,
        name: str,
        payload: bytes,
        artifact_type: str,
        media_type: str,
        payload_schema_version: str | None = None,
        parent_artifact_ids: list[str] | None = None,
        source_record_ids: list[str] | None = None,
        prompt_refs: list[dict[str, Any]] | None = None,
        model_refs: list[dict[str, Any]] | None = None,
        validator_refs: list[str] | None = None,
        langfuse_trace_ids: list[str] | None = None,
        created_by: str,
        sensitivity: str = "sanitized",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactManifest:
        if stage not in STAGE_DIRS:
            raise ValueError(f"unknown stage {stage!r}")
        if not name or Path(name).name != name:
            raise ValueError("artifact name must be one filename")
        relative = str(Path(STAGE_DIRS[stage]) / name).replace("\\", "/")
        final_path = self._safe_relative(relative)
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        with _filesystem_lock(self.run_dir / ".artifacts.lock"):
            if final_path.exists():
                existing = final_path.read_bytes()
                existing_digest = "sha256:" + hashlib.sha256(existing).hexdigest()
                if existing != payload:
                    raise ArtifactConflictError(
                        f"immutable artifact conflict at {relative}: {existing_digest} != {digest}"
                    )
            else:
                final_path.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(
                    dir=self.run_dir / ".staging", prefix="artifact-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temp_name, final_path)
                finally:
                    if os.path.exists(temp_name):
                        os.unlink(temp_name)
        manifest = ArtifactManifest(
            artifact_id=stable_id(
                "artifact",
                {"run_id": self.run_id, "path": relative, "content_hash": digest},
            ),
            artifact_type=artifact_type,
            relative_path=relative,
            media_type=media_type,
            content_hash=digest,
            byte_size=len(payload),
            payload_schema_version=payload_schema_version,
            parent_artifact_ids=parent_artifact_ids or [],
            source_record_ids=source_record_ids or [],
            prompt_refs=prompt_refs or [],
            model_refs=model_refs or [],
            validator_refs=validator_refs or [],
            langfuse_trace_ids=langfuse_trace_ids or [],
            created_by=created_by,
            sensitivity=sensitivity,
            metadata={"run_id": self.run_id, **(metadata or {})},
        )
        manifest.validate()
        event = {
            "event": "artifact.created",
            "run_id": self.run_id,
            "recorded_at": utc_now(),
            "artifact": manifest.to_dict(),
        }
        known = {row["artifact"]["artifact_id"] for row in self.events() if row.get("event") == "artifact.created"}
        if manifest.artifact_id not in known:
            self._append_event(event)
        self.materialize_summary()
        return manifest

    def put_json(
        self,
        *,
        stage: str,
        name: str,
        value: dict[str, Any] | list[Any],
        artifact_type: str,
        created_by: str,
        **kwargs: Any,
    ) -> ArtifactManifest:
        if isinstance(value, dict):
            schema_version = value.get("schema_version")
        else:
            schema_version = None
        payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        return self.put_bytes(
            stage=stage,
            name=name,
            payload=payload,
            artifact_type=artifact_type,
            media_type="application/json",
            payload_schema_version=schema_version,
            created_by=created_by,
            **kwargs,
        )

    def put_text(
        self,
        *,
        stage: str,
        name: str,
        text: str,
        artifact_type: str,
        created_by: str,
        **kwargs: Any,
    ) -> ArtifactManifest:
        return self.put_bytes(
            stage=stage,
            name=name,
            payload=text.encode("utf-8"),
            artifact_type=artifact_type,
            media_type="text/markdown; charset=utf-8" if name.endswith(".md") else "text/plain; charset=utf-8",
            created_by=created_by,
            **kwargs,
        )

    def events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        rows = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SchemaError("run event log is corrupt") from exc
        return rows

    def artifacts(self) -> list[ArtifactManifest]:
        return [
            ArtifactManifest.from_dict(event["artifact"])
            for event in self.events()
            if event.get("event") == "artifact.created"
        ]

    def materialize_summary(self) -> dict[str, Any]:
        events = self.events()
        artifacts = [
            event["artifact"] for event in events if event.get("event") == "artifact.created"
        ]
        summary = {
            "schema_version": "assessment-evolution-run/1",
            "run_id": self.run_id,
            "purpose": self.purpose,
            "event_count": len(events),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "updated_at": utc_now(),
        }
        payload = (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        fd, temp_name = tempfile.mkstemp(
            dir=self.run_dir / ".staging", prefix="manifest-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.summary_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return summary

    def verify(self) -> list[str]:
        errors: list[str] = []
        for artifact in self.artifacts():
            path = self._safe_relative(artifact.relative_path)
            if not path.exists():
                errors.append(f"missing {artifact.relative_path}")
                continue
            payload = path.read_bytes()
            digest = "sha256:" + hashlib.sha256(payload).hexdigest()
            if digest != artifact.content_hash:
                errors.append(f"hash mismatch {artifact.relative_path}")
            if len(payload) != artifact.byte_size:
                errors.append(f"size mismatch {artifact.relative_path}")
        return errors


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _event_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _filesystem_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
