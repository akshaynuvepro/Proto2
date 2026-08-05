"""Self-checks for the analysis worker. Run: uv run python test_worker.py"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import extract_local
import main


def _write_store(path: Path, count: int) -> None:
    messages = [
        {
            "id": f"m{i}",
            "ts": f"2026-08-05T12:00:{i:02d}.000Z",
            "day": "2026-08-05",
            "role": "user",
            "text": f"hello {i}",
            "tool": "live",
            "sessionId": "sess-worker",
        }
        for i in range(count)
    ]
    path.write_text(
        json.dumps({"schema": "proto-capture-conversations/1", "messages": messages}, indent=2),
        encoding="utf-8",
    )


def _busy_sleep(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def test_fingerprint_changes_with_store() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "conversations.json"
    _write_store(store, 1)
    with patch.object(main, "store_path", return_value=store):
        a = main.local_store_fingerprint()
        _busy_sleep(0.05)
        _write_store(store, 2)
        b = main.local_store_fingerprint()
        assert a != b, (a, b)


def test_wait_until_stable_debounce() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "conversations.json"
    _write_store(store, 1)

    def bump() -> None:
        _busy_sleep(0.25)
        _write_store(store, 2)

    with patch.object(main, "store_path", return_value=store):
        t = threading.Thread(target=bump)
        t.start()
        started = time.monotonic()
        fp = main.wait_until_stable(0.7)
        elapsed = time.monotonic() - started
        t.join()
        assert elapsed >= 0.7
        assert fp == main.local_store_fingerprint()


def test_worker_triggers_on_store_change() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "conversations.json"
    _write_store(store, 1)
    calls: list[dict] = []

    def fake_pipeline(**kwargs):
        calls.append(kwargs)

    args = Namespace(
        project="main",
        output=str(tmp / "out"),
        skills_output=str(tmp / "skills"),
        date="2026-08-05",
        source="local",
        force=False,
        limit=None,
        all_runs=False,
        interval=0.3,
        debounce=0.15,
        langsmith_interval=3600,
        no_run_on_start=True,
    )

    def mutate() -> None:
        _busy_sleep(0.5)
        _write_store(store, 3)

    stop_at = time.monotonic() + 3.0

    def sleep_maybe(seconds: float) -> None:
        if time.monotonic() >= stop_at or len(calls) >= 1:
            raise KeyboardInterrupt
        _busy_sleep(min(0.15, seconds))

    with (
        patch.object(main, "store_path", return_value=store),
        patch.object(main, "run_pipeline", side_effect=fake_pipeline),
        patch.object(main, "require_env"),
        patch.object(main, "load_env"),
        patch.object(time, "sleep", side_effect=sleep_maybe),
    ):
        threading.Thread(target=mutate, daemon=True).start()
        rc = main.run_worker(args)

    assert rc == 0
    assert len(calls) >= 1, calls
    assert calls[0]["source"] == "local"
    assert calls[0]["force"] is True
    assert calls[0]["command"] == "all"
    assert calls[0]["day"] == date(2026, 8, 5)


def test_worker_reruns_if_store_changes_during_pipeline() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "conversations.json"
    _write_store(store, 1)
    calls: list[int] = []

    def fake_pipeline(**kwargs):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            _write_store(store, 5)

    args = Namespace(
        project="main",
        output=str(tmp / "out"),
        skills_output=str(tmp / "skills"),
        date="2026-08-05",
        source="local",
        force=False,
        limit=None,
        all_runs=False,
        interval=0.2,
        debounce=0.0,
        langsmith_interval=3600,
        no_run_on_start=False,
    )

    def sleep_count(seconds: float) -> None:
        if len(calls) >= 2:
            raise KeyboardInterrupt
        _busy_sleep(0.05)

    with (
        patch.object(main, "store_path", return_value=store),
        patch.object(main, "run_pipeline", side_effect=fake_pipeline),
        patch.object(main, "require_env"),
        patch.object(main, "load_env"),
        patch.object(time, "sleep", side_effect=sleep_count),
    ):
        rc = main.run_worker(args)

    assert rc == 0
    assert len(calls) >= 2, f"expected re-run after mid-pipeline store change, got {calls}"


def test_extract_local_force_rewrites_on_growth() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = tmp / "conversations.json"
    out = tmp / "out"
    _write_store(store, 2)
    day = date(2026, 8, 5)
    extract_local.write_local_conversations(day=day, output_root=out, store=store, force=False)
    md = out / "conversations" / "local" / "2026-08-05" / "live_sess-worker.md"
    assert md.exists()
    first = md.read_text(encoding="utf-8")
    _write_store(store, 4)
    extract_local.write_local_conversations(day=day, output_root=out, store=store, force=True)
    second = md.read_text(encoding="utf-8")
    assert second != first
    assert "hello 3" in second


def main_checks() -> None:
    test_fingerprint_changes_with_store()
    print("ok fingerprint")
    test_wait_until_stable_debounce()
    print("ok debounce")
    test_extract_local_force_rewrites_on_growth()
    print("ok force rewrite")
    test_worker_triggers_on_store_change()
    print("ok trigger on change")
    test_worker_reruns_if_store_changes_during_pipeline()
    print("ok re-run after mid-pipeline change")
    print("all worker self-checks passed")


if __name__ == "__main__":
    main_checks()
