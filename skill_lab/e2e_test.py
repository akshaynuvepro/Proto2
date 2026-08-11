"""End-to-end functional test for skill_lab pipeline + ingest/split."""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from openrouter import load_dotenv
from skill_lab.ingest import parse_file, parse_paste, require_twenty
from skill_lab.models import Assessment
from skill_lab.pipeline import Pipeline
from skill_lab.split import split_train_holdout
from skill_lab.store import RunStore

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "data" / "skill_lab" / "inputs"
REPORT = ROOT / "data" / "skill_lab" / "e2e_report.json"


def ok(name: str, detail: str = "") -> dict:
    print(f"PASS  {name}" + (f" — {detail}" if detail else ""), flush=True)
    return {"name": name, "status": "pass", "detail": detail}


def fail(name: str, detail: str) -> dict:
    print(f"FAIL  {name} — {detail}", flush=True)
    return {"name": name, "status": "fail", "detail": detail}


def test_ingest_split() -> list[dict]:
    results: list[dict] = []
    # JSON ingest
    data = json.loads((INPUTS / "assessments.json").read_text(encoding="utf-8"))
    items = [
        Assessment(
            id=str(a["id"]),
            title=str(a.get("title") or a["id"]),
            body=str(a.get("body") or ""),
            source=str(a.get("source") or "json"),
        )
        for a in data
    ]
    try:
        twenty = require_twenty(items)
        results.append(ok("ingest_json_20", f"count={len(twenty)}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("ingest_json_20", str(exc)))
        return results

    # file ingest
    try:
        from_files: list[Assessment] = []
        for p in sorted(INPUTS.glob("asm_*.md")):
            from_files.extend(parse_file(p, start_idx=len(from_files) + 1))
        require_twenty(from_files)
        results.append(ok("ingest_md_files", f"count={len(from_files)}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("ingest_md_files", str(exc)))

    # paste with ---
    paste = "\n---\n".join(f"# Paste {i}\n\nBody {i}" for i in range(1, 21))
    try:
        pasted = require_twenty(parse_paste(paste))
        results.append(ok("ingest_paste_separators", f"count={len(pasted)}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("ingest_paste_separators", str(exc)))

    # reject <20
    try:
        require_twenty(items[:5])
        results.append(fail("reject_under_20", "expected ValueError"))
    except ValueError:
        results.append(ok("reject_under_20"))

    # split
    try:
        split = split_train_holdout(twenty, seed=42)
        assert len(split.train) == 10 and len(split.holdout) == 10
        ids = {a.id for a in split.train} | {a.id for a in split.holdout}
        assert len(ids) == 20
        results.append(ok("split_10_10", f"seed={split.seed}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("split_10_10", str(exc)))

    # store
    try:
        store = RunStore()
        store.save_assessments(twenty)
        store.save_split(split_train_holdout(twenty, seed=7))
        assert store.manifest_path.exists()
        results.append(ok("store_write", f"run={store.run_id}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("store_write", str(exc)))

    return results


def test_full_pipeline() -> list[dict]:
    results: list[dict] = []
    load_dotenv()
    data = json.loads((INPUTS / "assessments.json").read_text(encoding="utf-8"))
    items = [
        Assessment(
            id=str(a["id"]),
            title=str(a.get("title") or a["id"]),
            body=str(a.get("body") or ""),
            source=str(a.get("source") or "json"),
        )
        for a in data[:20]
    ]
    pipe = Pipeline(store=RunStore())
    t0 = time.time()

    try:
        split = pipe.set_assessments(items, seed=42)
        results.append(ok("pipeline_split", f"train={len(split.train)} holdout={len(split.holdout)}"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("pipeline_split", f"{exc}\n{traceback.format_exc()}"))
        return results

    try:
        skill = pipe.build_skill()
        assert skill.skill_md.strip(), "empty SKILL.md"
        assert "SKILL.md" in skill.files
        results.append(
            ok(
                "pipeline_create_skill",
                f"files={list(skill.files)} summary_len={len(skill.summary)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(fail("pipeline_create_skill", f"{exc}\n{traceback.format_exc()}"))
        return results

    try:
        generated = pipe.generate()
        assert len(generated) == 10
        nonempty = sum(1 for g in generated if len(g.body.strip()) > 200)
        results.append(ok("pipeline_generate_10", f"nonempty={nonempty}/10"))
    except Exception as exc:  # noqa: BLE001
        results.append(fail("pipeline_generate_10", f"{exc}\n{traceback.format_exc()}"))
        return results

    try:
        report = pipe.compare()
        assert "summary_markdown" in report
        auto = report.get("automatic_metrics") or {}
        assert "bleu" in auto and "embedding" in auto and "pairing" in auto
        assert auto["bleu"].get("corpus") is not None
        assert auto["embedding"].get("mean_cosine") is not None
        results.append(
            ok(
                "pipeline_compare_agent",
                f"overall_score={report.get('overall_score')} "
                f"bleu={auto['bleu'].get('corpus')} "
                f"embed={auto['embedding'].get('mean_cosine')} "
                f"fixes={len(report.get('priority_fixes') or [])}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(fail("pipeline_compare_agent", f"{exc}\n{traceback.format_exc()}"))
        return results

    try:
        improver, improved = pipe.improve()
        assert improver.strip()
        assert improved.skill_md.strip()
        results.append(
            ok(
                "pipeline_improve",
                f"improver_chars={len(improver)} improved_files={list(improved.files)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(fail("pipeline_improve", f"{exc}\n{traceback.format_exc()}"))
        return results

    elapsed = round(time.time() - t0, 1)
    results.append(ok("pipeline_elapsed_seconds", str(elapsed)))
    results.append(ok("pipeline_run_dir", str(pipe.store.root)))
    return results


def main() -> int:
    load_dotenv()
    all_results: list[dict] = []
    print("=== ingest/split/store ===", flush=True)
    all_results.extend(test_ingest_split())
    print("=== full LLM pipeline ===", flush=True)
    all_results.extend(test_full_pipeline())

    passed = sum(1 for r in all_results if r["status"] == "pass")
    failed = sum(1 for r in all_results if r["status"] == "fail")
    payload = {"passed": passed, "failed": failed, "results": all_results}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSUMMARY passed={passed} failed={failed} report={REPORT}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
