# Proto2 Migration Roadmap

## Purpose

This document maps the current conversation-to-sandbox-skill prototype to the
assessment-improvement architecture. It favors incremental replacement over a
large rewrite.

## Current Strengths to Retain

Proto2 already provides useful foundations:

- LangSmith extraction.
- Local agent conversation capture.
- Canonical Markdown transcript rendering.
- A polling worker with debounce and rerun behavior.
- Local artifact storage.
- Basic classification audit files.
- Skill package and catalog concepts.
- MCP read/write separation.
- A local analysis UI.
- Assert-based worker and skill self-checks.

These foundations need new domain contracts and validation, not wholesale
deletion.

## Current Behaviors to Replace

| Current behavior | Replacement |
|---|---|
| Group by opening prompt signature | Route by persona, assessment, evidence category, target skill, and domain |
| Classify into sandbox skills | Build approved evidence and benchmark items |
| Direct LLM merge into SKILL.md | Principle bank followed by SkillOpt |
| No validation-gated acceptance | Hard gates plus held-out downstream evaluation |
| One conversation interpretation | Per-trajectory extraction and hierarchical merge |
| No learner model | Strict comprehension-only learner pipeline |
| Console-oriented monitoring | Immutable lineage plus Langfuse |
| Catalog as deployment | SME-approved target release registry |

## Target Package Boundaries

The implementation should evolve toward these logical subsystems:

```text
assessment_evolution/
  ingestion/
  normalization/
  privacy/
  evidence/
  review/
  principles/
  bank/
  compiler/
  skillopt_env/
  target_evolution/
  evaluation/
  artifacts/
  observability/
  release/
```

This is a logical boundary, not a requirement to create every directory before
behavior exists.

## Migration of Existing Modules

### Extraction

Current LangSmith and local extraction can become source adapters.

Required changes:

- Emit canonical JSON in addition to human-readable Markdown.
- Add persona, assessment, target skill, domain, consent, and sensitivity.
- Preserve source message IDs and spans.
- Decouple local calendar date from UTC date.
- Treat source content as immutable.
- Record connector and normalizer versions.

### Conversation schema

Replace the Markdown-first shared schema with a canonical structured record.
Markdown remains a view generated from JSON.

### Classification

The current sandbox classifier becomes an evidence router:

- Resolve persona.
- Link assessment and target skill.
- Route SME versus learner extraction.
- Detect mixed and unknown records.
- Assign evidence categories and review queues.

Opening signature grouping may remain a deduplication feature but cannot define
assessment identity.

### Analysis

The current feedback JSON analyzer is replaced by:

- SME evidence extractor.
- Learner boundary classifier.
- Learner comprehension extractor.
- Evidence merger.
- Principle distiller.
- Judge/evaluation calls.

LLM call helpers should return structured usage, prompt version, trace, and
artifact metadata rather than only text.

### Skill update

The current direct merge path is retired for assessment evolution. Existing
generated sandbox skills remain readable but are not silently migrated.

New behavior:

1. Curate principle bank.
2. Compile seed improvement skill.
3. Invoke SkillOpt custom environment.
4. Store best skill and full run history.
5. Apply best skill to target envelopes in proposal mode.

### Worker

Retain polling, debounce, retry, and mid-run change detection. Replace one
monolithic forced pipeline with stage checkpoints and immutable run IDs.

Worker triggers:

- New source cutoff.
- New approved evidence.
- New domain profile.
- New target-skill version.
- Explicit optimization request.
- Scheduled evaluation or telemetry backfill.

Training should not trigger automatically from every appended message.

### MCP packages

`proto-capture` can remain a source, subject to persona and consent
metadata. Production SME/learner product connectors should not rely on an agent
voluntarily calling a capture tool.

`proto-skills` should eventually serve:

- Current approved improvement skill.
- Domain profiles.
- Release status.
- Target-skill proposals for authorized tooling.

It must not serve unvalidated candidates as approved skills.

### UI

Evolve the read-only analysis UI into views for:

- Run overview and stage state.
- Evidence candidates and source citations.
- SME review queues.
- Learner redaction and confusion clusters.
- Principle bank versions and Add/Rewrite/Remove decisions.
- SkillOpt history and validation curves.
- Original/candidate assessment comparison.
- Consumer matrix and negative transfer.
- Langfuse trace deep links.
- Release approval and rollback history.

Authentication and authorization become mandatory before real conversations
or assessment answers appear.

## New Public Contracts

Implementation should define versioned types for:

- `ConversationRecord`
- `SourceSpan`
- `SMEEvidence`
- `LearnerConfusionEvidence`
- `EvidenceReview`
- `EvidenceBundle`
- `AssessmentImprovementPrinciple`
- `PrincipleBankVersion`
- `TargetSkillEnvelope`
- `DomainProfile`
- `BenchmarkItem`
- `EvolutionResult`
- `EvaluationResult`
- `ArtifactManifest`
- `ReleaseProposal`

All structured files include `schema_version` and reject unknown major
versions.

## Phase 0: Foundation Decisions

Deliver:

- Final schema definitions.
- Artifact path and ID conventions.
- Privacy and retention policy mapping.
- Model/provider configuration abstraction.
- Prompt repository convention.
- Langfuse self-hosting configuration.
- SkillOpt dependency pin and compatibility check.

Exit criteria:

- Architecture and security review approved.
- Example artifacts validate.
- No unresolved ownership of SME review or release promotion.

## Phase 1: Artifact and Observability Foundation

Implement:

- Run IDs and immutable stage directories.
- Artifact safe writes, manifests, hashing, and lineage.
- Prompt registry in Git.
- Langfuse client wrapper.
- Session, trace, generation, metadata, and score conventions.
- Telemetry retry/backfill and content suppression.

Tests:

- Hash integrity.
- Resume.
- Concurrent safe writes.
- Telemetry outage.
- Redaction before tracing.

Exit criteria:

- A mock multi-stage run is fully reconstructable.
- Every mock LLM call has local and Langfuse lineage.

## Phase 2: Canonical Ingestion

Implement:

- LangSmith adapter.
- Local capture adapter.
- Canonical conversation JSON.
- Markdown view renderer.
- Persona and assessment metadata.
- Source-span mapping.
- Deterministic normalization.

Tests:

- Existing LangSmith shapes.
- Existing local capture shapes.
- Timezone boundaries.
- Missing metadata.
- Duplicate and changing source data.

Exit criteria:

- Current data can be re-extracted without losing provenance.

## Phase 3: Privacy and Evidence

Implement:

- Secret and PII detection.
- Learner solution-boundary classifier.
- SME extractor.
- Learner comprehension extractor.
- Evidence validators and review records.
- Aggregation and conflict detection.
- Review UI/API.

Use learner examples only as synthetic classifier tests until real learner
conversations arrive.

Exit criteria:

- Human-labeled evidence tests meet approved thresholds.
- No known learner solution false negatives in the release test set.
- SME can approve/reject and correct evidence.

## Phase 4: Principle Bank

Implement:

- Principle schema.
- Parallel distillation.
- Hierarchical merge.
- Keep/Add/Rewrite/Remove diagnoser and planner.
- Utility/diversity/coverage verification.
- Pareto selection.
- Bank version registry.
- Deterministic improvement-skill compiler.

Exit criteria:

- Every principle is evidence-backed.
- Rejected bank candidates remain inspectable.
- Compilation from the same bank is reproducible.

## Phase 5: SkillOpt Integration

Implement:

- Pinned SkillOpt dependency.
- Assessment-improver split loader.
- Rollout helper.
- Environment adapter.
- YAML config.
- Trajectory persistence.
- Resume and artifact indexing.

Use structurally diverse synthetic target fixtures with placeholder domain
content.

Exit criteria:

- Seed and candidate skills complete end-to-end rollouts.
- SkillOpt rejects non-improving candidates.
- `best_skill.md` and history are indexed in the run manifest.

## Phase 6: Evaluation

Implement:

- Target-skill hard validators.
- Assessment hard validators.
- Soft rubric and calibrated judges.
- Paired baseline/candidate generation.
- Consumer matrix.
- SkillLens-style delta, extraction efficacy, target evolvability, and negative
  transfer reports.
- Langfuse dataset experiments.

Exit criteria:

- Baseline results are reproducible.
- SME labels calibrate subjective judges.
- Validation and test remain isolated.

## Phase 7: Real AWS Staging

When external AWS skills become available:

1. Inventory formats, required sections, scripts, tools, and output contracts.
2. Create target-skill envelopes.
3. Create an authoritative AWS domain profile.
4. Add validators using approved AWS references and assessment policies.
5. Build train/validation/test items without leakage.
6. Run proposal-only evolution.
7. Conduct blind SME assessment comparisons.

Exit criteria:

- No synthetic result is represented as AWS factual validation.
- Real target contracts are preserved.
- SME approves a staged proposal.

## Phase 8: Learner Shadow Mode

Implement the real learner connector and run:

- Ingestion.
- Persona resolution.
- PII and solution redaction.
- Comprehension extraction.
- Aggregation.
- Review.

Do not feed learner evidence into optimization.

Exit criteria:

- Classifier precision and solution leakage meet policy.
- Learner clusters are meaningful to SMEs.
- Privacy and retention review passes.

## Phase 9: Learner-Informed Optimization

Enable only aggregated, SME-approved learner clusters.

Validate:

- Assessment clarity improves.
- Solution leakage stays zero.
- Difficulty and correctness do not regress.
- One learner cannot disproportionately influence a skill.

## Phase 10: Proposal-Only Production

Deliver:

- Release package.
- Approval workflow.
- Deployment handoff.
- Rollback registry.
- Production monitoring.

No unreviewed promotion is in scope.

## Compatibility Strategy

- Preserve current CLI commands during early phases where practical.
- Add new commands rather than silently changing old data meaning.
- Version new data roots separately from existing generated sandbox data.
- Provide explicit migration tooling for conversation records.
- Treat current skill catalog as legacy input/read-only until new registry is
  ready.
- Maintain legacy UI views while adding new review views.

## Suggested Command Surface

The final command names are illustrative but behavior is fixed:

```text
proto2 ingest --source langsmith|local|learner
proto2 normalize --run <id>
proto2 extract-evidence --run <id>
proto2 build-review --run <id>
proto2 curate-bank --bundle <id>
proto2 compile-improvement-skill --bank <id>
proto2 optimize --dataset <id>
proto2 evaluate --skill <path> --split validation|test
proto2 evolve-target --skill <path> --target <envelope>
proto2 prepare-release --evolution <id>
proto2 telemetry backfill --run <id>
```

Commands do not overwrite prior outputs and return run/artifact identifiers.

## Dependency Strategy

- Keep Proto2 Python version compatible with SkillOpt or isolate SkillOpt in a
  documented environment if dependency constraints conflict.
- Pin exact framework and SDK versions.
- Add Langfuse Python SDK compatible with the selected self-hosted server.
- Keep TypeScript MCP packages independent from optimizer dependencies.
- Record lockfile hashes in every optimization run.

## Migration Risks

| Risk | Response |
|---|---|
| Current data lacks persona metadata | Resolve or quarantine; do not infer silently |
| Existing direct skills are mistaken for validated artifacts | Label legacy and exclude from new release registry |
| SkillOpt dependency conflicts with Python 3.13 | Use a separate locked worker environment if needed |
| LLM cost grows through two-stage rollouts | Cache immutable baseline outputs and use staged budgets |
| Learner ingestion arrives before safety classifier | Run capture-only or shadow mode |
| External AWS format differs from fixtures | Adapter through envelope; do not rewrite core skill |
| Langfuse unavailable | Local authoritative artifacts and backfill |

## Implementation Completion Criteria

- The old direct rewrite path is not used for assessment releases.
- Real and synthetic data are distinguishable.
- All new public schemas are versioned.
- All stages persist intermediate output.
- SkillOpt validation gates select the best improvement skill.
- Consumption evaluation proves downstream impact.
- Langfuse traces every sanitized LLM operation.
- Learner solution content is excluded.
- SME approval controls evidence and promotion.
- Rollback can restore the prior target skill.
