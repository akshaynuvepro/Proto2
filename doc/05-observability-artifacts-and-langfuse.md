# Observability, Artifact Lineage, and Langfuse

## Purpose

Most stages use LLMs and are nondeterministic. Monitoring only the final
`best_skill.md` is insufficient. The system must reconstruct every input,
prompt, model call, transformation, score, review, and selection that produced
a release proposal.

Two linked systems provide that record:

- The local filesystem is the authoritative immutable artifact store.
- Self-hosted Langfuse is the searchable observability and evaluation surface.

## Principles

- Persist before progressing to the next stage.
- Never overwrite an artifact.
- Identify exact content with SHA-256.
- Link every output to parent artifacts.
- Use stable observation names, not model names.
- Trace LLM calls as generations.
- Treat telemetry failure as degraded operation, not data loss.
- Never trace raw PII or learner solution content.
- Make local-to-Langfuse lineage bidirectional.

## Artifact Manifest

Every stored artifact has a manifest entry.

### Field contract

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `artifact_id` | string | Yes | Stable logical identifier |
| `artifact_version` | integer | Yes | Immutable version |
| `artifact_type` | string | Yes | Canonical type |
| `relative_path` | string | Yes | Path below run root |
| `media_type` | string | Yes | JSON, Markdown, text, etc. |
| `content_hash` | string | Yes | SHA-256 |
| `byte_size` | integer | Yes | Integrity and budgeting |
| `schema_version` | string/null | Yes | Structured format |
| `parent_artifact_ids` | string[] | Yes | Direct lineage |
| `source_record_ids` | string[] | Yes | Origin identifiers |
| `prompt_refs` | object[] | Yes | Git and Langfuse prompt versions |
| `model_refs` | object[] | Yes | Provider, model, parameters |
| `validator_refs` | object[] | Yes | Validator versions |
| `langfuse_trace_ids` | string[] | Yes | Searchable trace links |
| `status` | enum | Yes | Complete, failed, quarantined |
| `created_at` | timestamp | Yes | Immutable |
| `created_by` | string | Yes | Component and version |
| `sensitivity` | enum | Yes | Restricted, sanitized, public |
| `metadata` | object | Yes | Safe, bounded attributes |

### Example

```json
{
  "artifact_id": "artifact_evidence_candidate_01J...",
  "artifact_version": 1,
  "artifact_type": "sme-evidence-candidate",
  "relative_path": "03-evidence-candidates/sme/ev_01J....json",
  "media_type": "application/json",
  "content_hash": "sha256:...",
  "byte_size": 4812,
  "schema_version": "sme-assessment-evidence/1",
  "parent_artifact_ids": ["artifact_sanitized_conv_01J..."],
  "source_record_ids": ["conv_01J..."],
  "prompt_refs": [
    {
      "name": "sme-evidence-extractor",
      "git_hash": "sha256:...",
      "langfuse_version": 7
    }
  ],
  "model_refs": [
    {
      "provider": "openrouter",
      "model": "configured-model",
      "temperature": 0.1
    }
  ],
  "validator_refs": ["sme-evidence-schema:v1"],
  "langfuse_trace_ids": ["trace-id"],
  "status": "complete",
  "created_at": "2026-08-07T12:00:00+05:30",
  "created_by": "evidence-extractor:v1",
  "sensitivity": "sanitized",
  "metadata": {
    "persona": "sme",
    "run_id": "run_01J..."
  }
}
```

## Run Manifest

The run manifest indexes:

- Run identity, purpose, status, and parent run.
- Git revision and dirty-state indicator.
- Dependency lock hashes.
- Configuration snapshot.
- Source cutoff and source hashes.
- Artifact manifest entries.
- Stage attempts and completion.
- Langfuse session and trace IDs.
- Cost, token, latency, and error totals.
- Review and promotion events.
- Resume checkpoints.

The run manifest is append-only at the event level. A materialized summary may
be regenerated from its event log.

## Safe Write Protocol

For each artifact:

1. Write to a staging path inside the same run filesystem.
2. Flush and close.
3. Calculate SHA-256 and byte size.
4. Validate schema and content.
5. Atomically rename to the final immutable path.
6. Append the artifact event to the run manifest.
7. Emit or update the linked Langfuse observation.

An existing final path with a different hash is a blocking integrity failure.

## Langfuse Deployment

The target is a self-hosted Langfuse deployment controlled by the
organization. Configuration uses environment variables and contains no
credentials in repository files.

Required configuration categories:

- Host/base URL.
- Public and secret keys.
- Environment name.
- Release/application version.
- Export timeout and queue limits.
- Content-capture policy.
- Dataset and prompt namespaces.

Development, staging, and production use distinct Langfuse environments or
projects according to organizational policy.

## Trace Hierarchy

### Sessions

Use one Langfuse `session_id` per pipeline run. This groups ingestion,
curation, optimization, evaluation, and release traces without forcing one
unmanageably large trace.

### Trace types

| Trace name | Scope |
|---|---|
| `conversation-processing` | One source conversation |
| `evidence-review-preparation` | One review batch |
| `principle-curation` | One bank proposal/verification cycle |
| `skillopt-rollout` | One optimizer step and benchmark item |
| `consumption-evaluation` | One target/consumer/item comparison |
| `target-skill-evolution` | One external target application |
| `release-preparation` | One proposed release |

### Stable observation names

Use these names independent of provider or model:

```text
conversation.load
conversation.normalize
conversation.redact
conversation.validate
evidence.persona.resolve
evidence.sme.extract
evidence.learner.classify
evidence.learner.redact-solution
evidence.learner.aggregate
evidence.merge
evidence.schema.validate
principle.distill
bank.diagnose
bank.add-candidates
bank.plan
bank.verify.utility
bank.verify.diversity
bank.verify.coverage
bank.select
improvement.compile
skillopt.evolve-target
skillopt.patch.validate
assessment.generate.baseline
assessment.generate.candidate
evaluation.hard-gates
evaluation.soft-scores
evaluation.consumer-matrix
release.prepare
release.review
```

Deterministic work uses spans or appropriate tool observations. LLM calls use
generations nested below their orchestrating span.

## Generation Capture

Every generation records:

- Sanitized role-labeled input.
- Sanitized output.
- Provider and exact model.
- Model parameters.
- Prompt name, Git content hash, Langfuse prompt version, and label.
- Start/end time and latency.
- Input, output, cached, and reasoning tokens when available.
- Calculated or reported cost.
- Retry number and preceding failure category.
- Parent artifact IDs and intended output artifact ID.
- Structured parse status.
- Finish reason.

Large payloads remain local. Langfuse receives a readable sanitized summary,
artifact hash, safe relative path, and selected structured fields.

## Propagated Metadata

Use low-cardinality stable observation names. Put run-specific values in
metadata:

| Metadata key | Example |
|---|---|
| `run_id` | `run_01J...` |
| `stage` | `evidence-extraction` |
| `artifact_id` | `artifact_01J...` |
| `artifact_hash` | `sha256:...` |
| `conversation_id` | Pseudonymous stable ID |
| `persona` | SME or learner |
| `evidence_bundle_id` | `bundle_01J...` |
| `principle_bank_version` | `bank:v4` |
| `improvement_skill_version` | `skill_v0012` |
| `target_skill_id` | External logical ID |
| `target_skill_hash` | Exact target input |
| `domain_profile_id` | `aws-profile:v1` |
| `dataset_id` | Benchmark dataset |
| `dataset_split` | Train, validation, test |
| `benchmark_item_id` | Stable item |
| `skillopt_epoch` | Integer |
| `skillopt_step` | Integer |
| `candidate_id` | Candidate skill or bank |
| `evaluation_profile` | Versioned rubric |
| `release_id` | Proposed release |

Metadata sent through propagated attributes must comply with Langfuse length
and type constraints. Full data remains in local artifacts.

## Tags

Apply known-at-start tags:

- `assessment-improver`
- `sme` or `learner`
- `train`, `validation`, or `test`
- `baseline` or `candidate`
- `synthetic-fixture` or `real-target`
- `development`, `staging`, or `production`

Results learned after execution are scores, not tags.

## Prompt Management

### Source of truth

Prompts are versioned files in Git. Each prompt has:

- Stable name.
- Purpose.
- Input variables.
- Output schema.
- Safety boundaries.
- Content hash.
- Change history.
- Test dataset.

### Langfuse mirror

On deployment or explicit sync:

1. Read the Git prompt.
2. Calculate its content hash.
3. Search the Langfuse prompt namespace for that hash.
4. Create a version if absent.
5. Apply environment labels only after prompt tests pass.
6. Record Langfuse version in the deployment manifest.

Runtime calls request an intended version/hash, not uncontrolled `latest`.
Local cached content remains available when Langfuse is unavailable.

## Langfuse Datasets and Experiments

The filesystem remains the dataset source of truth. Approved dataset versions
are mirrored to Langfuse to enable comparison views and review.

Dataset item metadata includes:

- Local dataset version and hash.
- Split and leakage group.
- Benchmark item ID.
- Assessment type and level.
- Target fixture family.
- Expected behavior references.
- Sensitivity classification.

Run experiments for:

- Extractor prompt/model comparisons.
- Learner classifier/redactor comparisons.
- Bank candidate utility comparisons.
- Seed versus current-best improvement skill.
- Original versus evolved target skill.
- Target consumer compatibility.
- Evaluation-prompt calibration.

Experiment names include dataset version, candidate version, evaluation
profile, and code release. Each item links to its trace and local output.

## Scores

### Trace and observation scores

| Score | Type | Target |
|---|---|---|
| `schema_valid` | Boolean | Extract/evolution output |
| `source_grounded` | Numeric | Evidence extraction |
| `solution_leakage` | Boolean/category | Learner processing and outputs |
| `contract_preserved` | Boolean | Target evolution |
| `hard_gates_passed` | Boolean | Rollout/release |
| `sme_adaptation` | Numeric | Candidate assessment |
| `assessment_utility` | Numeric | Candidate assessment |
| `learner_clarity` | Numeric/not-evaluated | Candidate assessment |
| `principle_diversity` | Numeric | Bank |
| `evidence_coverage` | Numeric | Bank |
| `negative_transfer` | Boolean | Consumer result |
| `review_decision` | Category | Human review |

Scores include evaluation source: deterministic code, judge model and prompt,
SME annotation, or aggregate computation.

### Human annotation

Use annotation queues for:

- SME evidence candidate review.
- Learner-confusion cluster review.
- Blind original-versus-candidate assessment comparison.
- Borderline release proposals.
- Evaluator disagreement calibration.

The authoritative review event is exported to the local run store with the
Langfuse annotation identifier.

## Privacy and Redaction

### Never send to Langfuse

- Raw names, emails, phone numbers, or account IDs.
- Secrets, credentials, tokens, or private endpoints.
- Raw learner answers or solution attempts.
- Restricted assessment answers or evaluator secrets.
- Unapproved raw attachments.
- Full local absolute paths containing personal information.

### Permitted after sanitization

- Pseudonymous IDs.
- Approved SME evidence excerpts.
- Redacted learner-comprehension excerpts.
- Safe prompts and outputs.
- Relative artifact paths.
- Hashes, schema versions, scores, model usage, and latency.

### Double validation

Sanitize before a trace is constructed and again before export. A second
detector blocks export if prohibited patterns remain. The local stage artifact
records that telemetry was suppressed.

## Telemetry Failure Behavior

Langfuse export is asynchronous and fail-open for pipeline computation:

1. Complete and persist the local artifact.
2. Mark the manifest event `telemetry_pending`.
3. Queue a bounded retry.
4. Continue unless observability is a configured release hard gate.
5. Flush at the end of short-lived processes.
6. Mark `telemetry_degraded` if retries expire.
7. Backfill from local manifests when service returns.

A production release cannot be approved until required trace links have been
backfilled or an authorized waiver is recorded.

## Dashboards

Create dashboards for:

- Volume by stage, persona, source, and status.
- Model cost and token usage by component.
- Latency and failure rate.
- Schema and grounding pass rates.
- SME acceptance and correction rates.
- Learner classifier precision and leakage incidents.
- Bank utility/diversity/coverage over versions.
- SkillOpt train and validation history.
- Baseline/candidate assessment deltas.
- Negative transfer by target consumer.
- Release proposal and approval status.

## Alerts

Alert on:

- Any learner solution leakage.
- Any raw PII export block.
- Sudden extractor grounding decline.
- Hard-gate pass-rate regression.
- Negative-transfer increase.
- Cost or token-budget breach.
- Repeated model/provider retries.
- Missing trace linkage for completed artifacts.
- Artifact hash mismatch.
- Langfuse exporter backlog over threshold.

Threshold values are environment configuration and versioned with the
monitoring profile.

## Retention

Retention classes are explicit:

| Class | Example | Policy |
|---|---|---|
| Restricted raw | Source conversations | Shortest approved retention, strict access |
| Sanitized evidence | Approved excerpts and schemas | Product learning retention |
| Optimization | Prompts, candidates, assessments | Run and reproducibility retention |
| Release | Best skills, patches, reports | Long-term version history |
| Telemetry | Langfuse trace data | Organizational observability policy |

Deletion requests create tombstone events and preserve only non-reversible
hash/lineage information where legally permitted.

## Observability Acceptance Criteria

- Every LLM call appears as a generation or has a recorded suppression reason.
- Every generation identifies prompt and model versions.
- Every final artifact links to parent artifacts and Langfuse traces.
- Every Langfuse trace links back to safe local artifact IDs and hashes.
- Token, cost, latency, retry, and parse status are available.
- Raw PII and learner solution content do not appear in Langfuse.
- A Langfuse outage does not lose authoritative work.
- Local artifacts can backfill missing telemetry.
- Dataset experiment results can compare baseline and candidate versions.
