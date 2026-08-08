# Implementation and Operations

## Scope

The executable implementation lives in the assessment_evolution package. It
runs alongside the legacy Proto2 sandbox-skill pipeline and does not change
main.py, existing MCP capture, or data/skills.

Implemented capabilities:

- Canonical SME and learner conversation ingestion.
- Versioned schemas and strict validation.
- PII, secret, learner-answer, strategy, code, and hint redaction.
- SME evidence and learner-comprehension extraction.
- Immutable review events and reviewed evidence copies.
- Three-distinct-learner aggregation and SME cluster review.
- Immutable evidence bundles.
- Principle distillation, multi-objective bank curation, Pareto selection,
  and deterministic compilation.
- One generic assessment-improvement best_skill.md.
- Complete target envelopes, reversible patches, reconstruction, and
  deterministic compatibility gates.
- Paired baseline/candidate evaluation and transfer metrics.
- A SkillOpt 0.2 loader, rollout, adapter, config, trajectory store, and
  launcher.
- Optional Langfuse v4 tracing with content suppression and local retry data.
- Proposal-only releases.
- An authenticated review API and Assessment Evolution UI tab.
- Synthetic train, validation, and test fixtures.

The repository cannot perform real AWS validation until the external AWS
assessment skill, approved AWS domain profile, approved evidence, domain
validators, model credentials, and self-hosted Langfuse are supplied.
Synthetic fixtures are labeled and are never AWS evidence.

## Package Map

| Path | Responsibility |
|---|---|
| assessment_evolution/schemas.py | Public versioned contracts |
| assessment_evolution/artifacts.py | Immutable run store, hashes, event log |
| assessment_evolution/normalization.py | Source adapters |
| assessment_evolution/privacy.py | Privacy and learner-solution boundary |
| assessment_evolution/evidence.py | Extraction, review, aggregation, bundle |
| assessment_evolution/principles.py | Distillation and bank curation |
| assessment_evolution/compiler.py | Bank to generic improvement skill |
| assessment_evolution/evolution.py | Target patch and hard gates |
| assessment_evolution/evaluation.py | Paired scoring and transfer report |
| assessment_evolution/llm.py | Structured OpenRouter generation |
| assessment_evolution/observability.py | Optional Langfuse v4 tracing |
| assessment_evolution/pipeline.py | Resumable orchestration |
| assessment_evolution/skillopt_env | SkillOpt custom environment |
| prompts/assessment_evolution | Git-authoritative prompts |
| fixtures/assessment_improver | Synthetic SkillOpt split data |
| configs/assessment_improver | SkillOpt configuration |

## Installation

~~~powershell
uv sync
Copy-Item .env.example .env
~~~

Offline normalization, redaction, review, curation, compilation, and tests do
not need provider credentials.

Model-backed stages use OPENROUTER_API_KEY, OPENROUTER_BASE_URL, and
ASSESSMENT_EVOLUTION_MODEL. Langfuse uses LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL. SkillOpt uses the provider
variables required by the model backend selected in its config.

## Run Lifecycle

Create a run:

~~~powershell
uv run proto2-evolve init-run
~~~

Use the returned run ID in later commands:

~~~powershell
uv run proto2-evolve ingest --run <run-id> --source langsmith-markdown --input <sme-directory> --persona sme --allow-llm --allow-telemetry
uv run proto2-evolve ingest --run <run-id> --source learner-markdown --input <learner-directory> --persona learner --allow-llm
uv run proto2-evolve sanitize --run <run-id>
uv run proto2-evolve extract-evidence --run <run-id> --model
uv run proto2-evolve status --run <run-id>
~~~

The model option affects SME extraction. The deterministic learner safety
boundary runs before learner evidence can be admitted.

## Evidence Review

Start the local review UI with an explicit token:

~~~powershell
$env:PROTO_REVIEW_TOKEN = "<strong-local-token>"
uv run python ui/server.py
~~~

Open http://127.0.0.1:8765 and choose Assessment Evolution. The authenticated
review request creates a review event and a new reviewed artifact. It never
edits the original candidate.

CLI review:

~~~powershell
uv run proto2-evolve review-evidence --run <run-id> --evidence-id <id> --decision approved --reviewer-id <id> --reviewer-role sme --reason source_matches
~~~

## Learner Aggregation

~~~powershell
uv run proto2-evolve aggregate-learners --run <run-id> --minimum-learners 3
uv run proto2-evolve review-cluster --run <run-id> --cluster-id <id> --decision approved --reviewer-id <sme-id>
~~~

Only solution-free clusters supported by three distinct pseudonymous learners
are created by default. A cluster remains unusable until SME approval.

## Principle Bank and Compilation

~~~powershell
uv run proto2-evolve build-bundle --run <run-id> --domain-profile-id <profile-id> --target-scope "aws-assessment-*" --split-manifest <split-id>
uv run proto2-evolve distill-principles --run <run-id>
uv run proto2-evolve review-principle --run <run-id> --principle-id <id> --decision approved --reviewer-id <id> --reviewer-role sme
uv run proto2-evolve curate-bank --run <run-id> --evidence-bundle-id <bundle-id> --measured-utility 0.0
uv run proto2-evolve compile-skill --run <run-id> --bank-id <bank-id>
~~~

Compilation writes 07-compiled-skill/best_skill.md and a compilation manifest.
The same selected bank and seed compile deterministically.

## SkillOpt Optimization

Synthetic fixtures are under:

~~~text
fixtures/assessment_improver/train
fixtures/assessment_improver/val
fixtures/assessment_improver/test
~~~

Run the pinned launcher:

~~~powershell
uv run proto2-skillopt --config configs/assessment_improver/default.yaml --cfg-options env.out_root=data/assessment-evolution/skillopt-runs
~~~

For each benchmark item the environment:

1. Uses the candidate improvement skill to evolve the complete target skill.
2. Parses the complete evolved skill and structured patch.
3. Applies deterministic evolution hard gates.
4. Generates baseline and candidate assessments under paired configuration.
5. Applies assessment gates and weighted scoring.
6. Reports baseline, candidate, delta, and negative transfer.
7. Persists the reflection trajectory and intermediate outputs.

The reflection trajectory is stored at
predictions/<item-id>/conversation.json. The default optimization config does
not enable final test evaluation.

SkillOpt 0.2 has no external environment entry-point registry. The launcher
performs the smallest pinned registration and delegates to the unmodified
SkillOpt trainer. It fails if the installed framework no longer matches the
0.2 registry contract.

## External Target Evolution

Direct evolution requires:

- A target envelope conforming to target-assessment-skill-envelope/1.
- An approved profile conforming to assessment-domain-profile/1.
- An evidence object with an items array containing only approved evidence
  and reviewed learner clusters.
- The optimized SkillOpt best_skill.md.

~~~powershell
uv run proto2-evolve evolve-target --run <run-id> --target-envelope <target.json> --domain-profile <profile.json> --evidence <evidence.json> --improvement-skill <best-skill.md>
~~~

If a model proposal fails a deterministic gate, its patch is discarded, the
original target is retained, and the decision becomes needs_review.

## Release Boundary

Release preparation creates a proposal and never deploys:

~~~powershell
uv run proto2-evolve prepare-release --run <run-id> --evolution-result-id <artifact-id> --target-skill-id <target-id> --prior-version v1 --proposed-version v2 --evaluation-id <evaluation-id> --rollback '{"previous_version":"v1","owner":"assessment-team"}'
~~~

Promotion requires approved release evidence and a separate controlled
deployment handoff.

Review the proposal without deploying it:

~~~powershell
uv run proto2-evolve review-release --run <run-id> --release-id <release-id> --decision approved --reviewer-id <sme-id> --reviewer-role sme
~~~

Mirror Git-authoritative prompts or backfill queued trace metadata after
Langfuse becomes available:

~~~powershell
uv run proto2-evolve sync-prompts --run <run-id> --label staging
uv run proto2-evolve telemetry-backfill --run <run-id>
~~~

## Artifact Layout

~~~text
data/assessment-evolution/runs/<run-id>/
  manifest.events.jsonl
  manifest.json
  telemetry.pending.jsonl
  00-input/
  01-normalized/
  02-sanitized/
  03-evidence-candidates/
  04-approved-evidence/
  05-principle-candidates/
  06-principle-bank/
  07-compiled-skill/
  08-skillopt/
  09-evaluation/
  10-release/
~~~

Final artifact paths are immutable. Reusing a path with different content is
an integrity failure. The event log is authoritative; manifest.json is its
materialized view.

## Verification

~~~powershell
python -m unittest -v test_assessment_evolution.py
python -m compileall -q assessment_evolution assessment_main.py
npm run build --prefix capture
npm run build --prefix skills-mcp
~~~

The offline suite covers contracts, deterministic IDs, privacy, learner
solution exclusion, aggregation thresholds, review immutability, artifact
conflicts, path traversal, principle curation, compilation, exact patch
reconstruction, immutable sections, negative transfer, and the governed flow
through best_skill.md.
