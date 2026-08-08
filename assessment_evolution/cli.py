"""Command-line surface for evidence-governed assessment evolution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore, new_run_id
from .pipeline import AssessmentEvolutionPipeline
from .prompts import list_prompts


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "data" / "assessment-evolution"


def _json_value(value: str) -> Any:
    return json.loads(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proto2-evolve",
        description="Evidence-governed assessment skill optimization.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-run", help="Create one immutable pipeline run.")
    init.add_argument("--purpose", default="assessment-evolution")

    status = sub.add_parser("status", help="Show run artifacts and integrity.")
    status.add_argument("--run", required=True)

    ingest = sub.add_parser("ingest", help="Normalize captured conversations.")
    ingest.add_argument("--run", required=True)
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument(
        "--source",
        choices=["local", "langsmith-markdown", "markdown", "learner-markdown", "canonical"],
        required=True,
    )
    ingest.add_argument("--persona", choices=["sme", "learner", "mixed", "unknown"], required=True)
    ingest.add_argument("--retention-class", default="assessment-research-approved")
    ingest.add_argument("--allow-llm", action="store_true")
    ingest.add_argument("--allow-telemetry", action="store_true")

    sanitize = sub.add_parser("sanitize", help="Redact normalized conversations.")
    sanitize.add_argument("--run", required=True)

    extract = sub.add_parser("extract-evidence", help="Extract pending evidence.")
    extract.add_argument("--run", required=True)
    extract.add_argument("--model", action="store_true", help="Use model-backed SME extraction.")

    review = sub.add_parser("review-evidence", help="Record one immutable evidence review.")
    review.add_argument("--run", required=True)
    review.add_argument("--evidence-id", required=True)
    review.add_argument(
        "--decision",
        choices=["approved", "approved_with_edits", "rejected", "duplicate", "deferred", "superseded"],
        required=True,
    )
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--reviewer-role", required=True)
    review.add_argument("--reason", action="append", required=True)
    review.add_argument("--comment")
    review.add_argument("--corrections", type=_json_value, default={})

    aggregate = sub.add_parser("aggregate-learners", help="Build recurring confusion clusters.")
    aggregate.add_argument("--run", required=True)
    aggregate.add_argument("--minimum-learners", type=int, default=3)

    review_cluster = sub.add_parser("review-cluster", help="SME review a learner cluster.")
    review_cluster.add_argument("--run", required=True)
    review_cluster.add_argument("--cluster-id", required=True)
    review_cluster.add_argument(
        "--decision",
        choices=["approved", "approved_with_edits", "rejected", "deferred"],
        required=True,
    )
    review_cluster.add_argument("--reviewer-id", required=True)
    review_cluster.add_argument("--comment")

    bundle = sub.add_parser("build-bundle", help="Freeze approved evidence for a run.")
    bundle.add_argument("--run", required=True)
    bundle.add_argument("--domain-profile-id", required=True)
    bundle.add_argument("--target-scope", action="append", required=True)
    bundle.add_argument("--split-manifest", required=True)

    distill = sub.add_parser("distill-principles", help="Create evidence-backed principle candidates.")
    distill.add_argument("--run", required=True)

    review_principle = sub.add_parser("review-principle", help="Review a principle candidate.")
    review_principle.add_argument("--run", required=True)
    review_principle.add_argument("--principle-id", required=True)
    review_principle.add_argument(
        "--decision",
        choices=["approved", "approved_with_edits", "rejected", "deferred"],
        required=True,
    )
    review_principle.add_argument("--reviewer-id", required=True)
    review_principle.add_argument("--reviewer-role", required=True)

    curate = sub.add_parser("curate-bank", help="Select an approved principle bank.")
    curate.add_argument("--run", required=True)
    curate.add_argument("--evidence-bundle-id", required=True)
    curate.add_argument("--measured-utility", type=float, default=0.0)
    curate.add_argument("--risk-penalty", type=float, default=0.0)

    compile_parser = sub.add_parser("compile-skill", help="Compile one generic improvement skill.")
    compile_parser.add_argument("--run", required=True)
    compile_parser.add_argument("--bank-id", required=True)
    compile_parser.add_argument("--token-budget", type=int, default=8000)

    evolve = sub.add_parser("evolve-target", help="Produce a proposal for an external target skill.")
    evolve.add_argument("--run", required=True)
    evolve.add_argument("--target-envelope", type=Path, required=True)
    evolve.add_argument("--domain-profile", type=Path, required=True)
    evolve.add_argument("--evidence", type=Path, required=True)
    evolve.add_argument("--improvement-skill", type=Path)

    release = sub.add_parser("prepare-release", help="Create a proposal-only release package.")
    release.add_argument("--run", required=True)
    release.add_argument("--evolution-result-id", required=True)
    release.add_argument("--target-skill-id", required=True)
    release.add_argument("--prior-version", required=True)
    release.add_argument("--proposed-version", required=True)
    release.add_argument("--evaluation-id", action="append", required=True)
    release.add_argument("--rollback", type=_json_value, required=True)

    release_review = sub.add_parser("review-release", help="Approve or reject a release proposal.")
    release_review.add_argument("--run", required=True)
    release_review.add_argument("--release-id", required=True)
    release_review.add_argument("--decision", choices=["approved", "rejected"], required=True)
    release_review.add_argument("--reviewer-id", required=True)
    release_review.add_argument("--reviewer-role", default="sme")
    release_review.add_argument("--comment")

    prompt_sync = sub.add_parser("sync-prompts", help="Mirror Git prompts to Langfuse.")
    prompt_sync.add_argument("--run", required=True)
    prompt_sync.add_argument("--label")

    backfill = sub.add_parser("telemetry-backfill", help="Backfill locally queued Langfuse metadata.")
    backfill.add_argument("--run", required=True)

    return parser


def _pipeline(root: Path, run_id: str) -> AssessmentEvolutionPipeline:
    run_dir = root / "runs" / run_id
    if not run_dir.exists():
        raise SystemExit(f"run not found: {run_id}")
    return AssessmentEvolutionPipeline(ArtifactStore(root, run_id))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "init-run":
        run_id = new_run_id(args.purpose)
        ArtifactStore(root, run_id, purpose=args.purpose)
        print(json.dumps({"run_id": run_id, "root": str(root)}))
        return
    pipeline = _pipeline(root, args.run)
    if args.command == "status":
        summary = pipeline.store.materialize_summary()
        summary["integrity_errors"] = pipeline.store.verify()
        summary["telemetry_pending"] = len(pipeline.observability.pending_events())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "ingest":
        value = pipeline.ingest(
            args.input,
            source=args.source,
            persona=args.persona,
            consent={
                "assessment_improvement": True,
                "llm_processing": args.allow_llm,
                "telemetry_redacted": args.allow_telemetry,
            },
            retention_class=args.retention_class,
        )
    elif args.command == "sanitize":
        value = pipeline.sanitize()
    elif args.command == "extract-evidence":
        value = pipeline.extract_evidence(use_model=args.model)
    elif args.command == "review-evidence":
        value = pipeline.review_candidate(
            evidence_id=args.evidence_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
            reason_codes=args.reason,
            comment=args.comment,
            field_corrections=args.corrections,
        )
    elif args.command == "aggregate-learners":
        value = pipeline.aggregate_learners(
            minimum_distinct_learners=args.minimum_learners
        )
    elif args.command == "review-cluster":
        value = pipeline.review_cluster(
            cluster_id=args.cluster_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            comment=args.comment,
        )
    elif args.command == "build-bundle":
        value = pipeline.build_bundle(
            domain_profile_id=args.domain_profile_id,
            target_scope=args.target_scope,
            split_manifest=args.split_manifest,
        )
    elif args.command == "distill-principles":
        value = pipeline.distill_principles()
    elif args.command == "review-principle":
        value = pipeline.review_principle(
            principle_id=args.principle_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
        )
    elif args.command == "curate-bank":
        value = pipeline.curate_bank(
            evidence_bundle_id=args.evidence_bundle_id,
            measured_utility=args.measured_utility,
            risk_penalty=args.risk_penalty,
        )
    elif args.command == "compile-skill":
        value = pipeline.compile_skill(
            bank_id=args.bank_id, token_budget=args.token_budget
        )
    elif args.command == "evolve-target":
        value = pipeline.evolve_target(
            target_envelope_path=args.target_envelope,
            domain_profile_path=args.domain_profile,
            evidence_path=args.evidence,
            improvement_skill_path=args.improvement_skill,
        )
    elif args.command == "prepare-release":
        value = pipeline.prepare_release(
            evolution_result_id=args.evolution_result_id,
            target_skill_id=args.target_skill_id,
            prior_version=args.prior_version,
            proposed_version=args.proposed_version,
            evaluation_ids=args.evaluation_id,
            rollback=args.rollback,
        )
    elif args.command == "review-release":
        value = pipeline.review_release(
            release_id=args.release_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
            comment=args.comment,
        )
    elif args.command == "sync-prompts":
        value = pipeline.observability.sync_prompts(
            list_prompts(), label=args.label
        )
    elif args.command == "telemetry-backfill":
        value = pipeline.observability.backfill()
    else:
        raise AssertionError(args.command)
    print(json.dumps({"run_id": args.run, "result": value}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
