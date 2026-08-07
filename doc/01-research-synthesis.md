# Research Synthesis: SkillOpt, SkillLens, SkillBrew, and Langfuse

## Purpose

This document translates four research and platform approaches into one
assessment-skill evolution architecture. The approaches solve different
problems and must not be collapsed into one undifferentiated "self-improvement"
step.

The system's desired output is a reusable assessment-improvement skill. That
skill is applied to an external assessment-generation skill, such as an AWS
assessment skill. The real measure of quality is the assessment produced after
that evolution, not how polished either skill document appears.

## Research Method

The design uses primary project repositories, project documentation, and
papers available as of August 2026:

- [SkillOpt repository](https://github.com/microsoft/SkillOpt)
- [SkillOpt custom benchmark guide](https://github.com/microsoft/SkillOpt/blob/main/docs/guide/new-benchmark.md)
- [SkillLens repository](https://github.com/microsoft/SkillLens)
- [SkillLens project page](https://microsoft.github.io/SkillLens/)
- [SkillLens paper](https://arxiv.org/abs/2605.23899)
- [SkillBrew paper](https://arxiv.org/abs/2605.29440)
- [Langfuse documentation](https://langfuse.com/docs)

Research findings are treated as architectural evidence, not as guarantees for
this assessment domain. Every adopted idea must be validated against the
project's own SME evidence, target skills, models, and scoring system.

## SkillOpt

### What SkillOpt Contributes

SkillOpt treats a natural-language skill document as the trainable state of a
frozen target agent. It runs tasks with the current skill, reflects on scored
trajectories, proposes bounded textual edits, and accepts a candidate only
through a validation gate. Its deployable artifact is `best_skill.md`.

The important properties for this project are:

1. The underlying model can remain fixed while the skill changes.
2. Optimization is driven by task outcomes and trajectories.
3. Training, validation, and test data have different responsibilities.
4. Candidate edits are not automatically accepted.
5. Rejected edits remain useful negative evidence.
6. The best validated skill can be deployed without optimizer memory.
7. Training runs preserve history, candidate versions, step artifacts, and
   resumable runtime state.

### Required Custom Environment

SkillOpt's custom benchmark contract requires:

- A split data loader.
- A rollout helper that runs and scores each item.
- An environment adapter that connects the loader and rollout lifecycle.
- A configuration that identifies the environment, models, seed skill, and
  optimization settings.
- A persisted conversation trajectory for every result used by reflection.
- At least an item identifier plus hard and soft reward values.

For this project, one rollout cannot stop after rewriting the target skill. It
must perform a downstream test:

1. Give the candidate improvement skill a target assessment skill, domain
   profile, compatibility manifest, and approved evidence.
2. Produce a proposed evolved target skill.
3. Generate an assessment from the original target skill.
4. Generate the same assessment from the evolved target skill.
5. Score both outputs against the same rubric and expected behaviors.
6. Return the delta and full trajectory to SkillOpt.

This makes SkillOpt optimize for practical assessment outcomes instead of
Markdown similarity.

### What Is Adopted Directly

- SkillOpt is the only optimizer dependency.
- Its train, validation, and test lifecycle is authoritative.
- Its candidate history and `best_skill.md` output are retained.
- The assessment-improver integration follows the public custom-environment
  contract rather than modifying SkillOpt internals.

### What Is Not Delegated to SkillOpt

- Raw conversation ingestion.
- PII and solution-content redaction.
- SME approval.
- Learner-confusion aggregation.
- Principle-bank curation.
- Production promotion of an external AWS skill.
- The definition of assessment-quality metrics.

## SkillLens

### Lifecycle Model

SkillLens studies the full lifecycle:

```text
experience generation -> schema normalization -> skill extraction -> skill consumption
```

That lifecycle is directly useful. Proto2 currently jumps from transcripts to
skill rewriting. The target design introduces explicit normalized experience,
evidence, extraction, and consumption stages.

### Findings Applied to This Project

#### Skills Can Cause Negative Transfer

SkillLens reports that generated skills help many extractor-target pairs but
can hurt others. Therefore:

- A skill must be evaluated against each supported consumer model or harness.
- A result from one AWS skill shape cannot establish compatibility with all AWS
  skills.
- Promotion requires a target-consumption matrix, not one aggregate score.
- A generic improvement skill must be tested with different target structures,
  assessment types, and domain profiles.

#### Strong Executors Are Not Necessarily Strong Extractors

The best assessment generator may not be the best evidence extractor.
Extractor and generator model choices are configured separately and compared
empirically.

#### Experience Composition Matters

Successful experiences anchor useful procedure. Failures reveal breakdowns.
All-failure pools performed poorly in the SkillLens study, and the best ratio
varied by domain.

The project therefore retains:

- SME final assessments and positive decisions.
- SME corrections, rejected drafts, and explicit critique.
- Learner comprehension failures.
- Successful assessment interactions when available.

No fixed universal success/failure ratio is assumed. The ratio is reported per
dataset version and evaluated through ablation experiments.

#### Surface Plausibility Is Not Utility

SkillLens found that attractive formatting and an LLM's aesthetic preference
did not reliably predict downstream utility. Accordingly:

- Formatting compliance is only a hard contract check.
- LLM judging is never the only acceptance signal.
- Deterministic checks and downstream assessment rollouts are mandatory.
- SME blind preference is used as human evidence, not as the entire score.

#### Three Useful Textual Dimensions

SkillLens identifies three dimensions associated with useful skills:

1. Failure-mechanism encoding.
2. Actionable specificity.
3. A blacklist of high-risk actions.

These become mandatory fields in every internal improvement principle and
mandatory sections in the seed improvement skill.

### Metrics Adapted from SkillLens

| Metric | Assessment-system interpretation |
|---|---|
| Performance delta | Evolved-target assessment score minus original-target score |
| Extraction efficacy | Average downstream delta for evidence extracted by one extractor configuration |
| Target evolvability | Average downstream delta for one target model or skill family across extractors |
| Negative-transfer rate | Fraction of evaluated target scenarios where the evolved skill scores lower |
| Consumption success | Whether the target agent can execute the improvement instructions correctly |

### Integration Strategy

SkillLens is not introduced as a runtime dependency in the first version.
Proto2 adopts its unified trajectory concept, parallel extraction pattern,
hierarchical merge, lifecycle measurements, and consumer matrix.

## SkillBrew

### Problem Addressed

Continual systems often append every newly discovered rule. The result becomes
redundant, contradictory, outdated, expensive to retrieve, and difficult to
validate. SkillBrew treats an entire skill bank as the optimization object.

Its three primary objectives are:

- **Utility:** Does the bank help the agent perform?
- **Diversity:** Does the bank avoid redundant principles?
- **Coverage:** Does the bank cover the query or task distribution?

SkillBrew uses a support/query separation and a propose-then-verify loop. Its
principal operations are Add, Rewrite, and Remove. This project also records
Keep explicitly for auditability.

### Assessment Principle Bank

The project uses a private, versioned principle bank before compiling the
single deployable improvement skill. Each principle includes:

- Title.
- Executable principle.
- When it applies.
- Failure mechanism.
- Concrete remedy.
- High-risk action blacklist.
- Approved evidence identifiers.
- Positive and negative examples.
- Confidence and review status.
- Utility history.
- Covered assessment/evidence clusters.
- Redundancy and contradiction links.
- Version and parent lineage.

### Curation Operations

| Operation | Use |
|---|---|
| Add | Approved evidence reveals an uncovered recurring failure or positive SME procedure |
| Rewrite | A principle is useful but generic, ambiguous, conflicting, or incomplete |
| Remove | A principle is harmful, obsolete, disproven, redundant, or outside scope |
| Keep | Evidence and downstream utility continue to support the current form |

### Multi-Objective Selection

Utility is a hard constraint: a bank candidate that lowers held-out downstream
utility cannot win because it is more diverse or covers more clusters.

Among candidates satisfying the utility constraint, selection considers:

- Semantic and lexical redundancy.
- Coverage of approved SME decision patterns.
- Coverage of approved learner-confusion clusters.
- Coverage of target-skill shapes and assessment types.
- Principle count and compiled token budget.
- Contradiction and staleness penalties.

The selection process persists all candidate banks and their Pareto positions.
This prevents rejected knowledge from disappearing without explanation.

### Integration Strategy

The published SkillBrew paper describes an approach but does not link a
production package selected for this project. The system implements the
research pattern locally rather than adding a runtime dependency.

## Langfuse

### Responsibilities

Langfuse supplies observability, prompt correlation, cost and latency tracking,
experiments, scores, and review navigation. It is not the authoritative
artifact store.

The authoritative record remains the versioned local filesystem because it
must support:

- Offline reconstruction.
- Exact hashes.
- Large artifacts.
- Rejected candidate retention.
- Resume after observability outages.
- Auditable links from a release to its source evidence.

### Data Model Mapping

| Langfuse object | Project mapping |
|---|---|
| Session | One pipeline or optimization run |
| Trace | One conversation transformation, bank proposal, rollout item, or release application |
| Span | One deterministic processing stage |
| Generation | One LLM call |
| Dataset | Mirrored benchmark or review dataset |
| Experiment | Baseline/candidate comparison |
| Score | Hard gate, quality measure, or review result |
| Prompt version | Mirror of one Git-versioned prompt |

### Privacy Position

Langfuse is self-hosted. It receives sanitized prompts and outputs, stable
artifact identifiers, hashes, and safe relative paths. Raw PII, secrets,
unapproved learner evidence, and learner solution spans are not traced.

### Prompt Position

Prompt files in Git are the source of truth. Their content hash and repository
revision identify them. Matching prompt versions are mirrored into Langfuse
and linked to generations for analysis.

## Combined Architecture

| Stage | Primary influence | Output |
|---|---|---|
| Capture and normalize | Proto2 + SkillLens | Canonical trajectories |
| Extract evidence | SkillLens | SME and learner evidence candidates |
| Review evidence | Product governance | Approved evidence bundle |
| Distill principles | SkillLens meta-skill findings | Evidence-backed principles |
| Curate bank | SkillBrew | Selected principle-bank version |
| Compile seed | Local compiler | Compact improvement skill |
| Optimize | SkillOpt | Validated `best_skill.md` |
| Evaluate consumption | SkillLens | Cross-target delta matrix |
| Observe | Langfuse | Traces, costs, scores, and experiment comparisons |
| Promote | SME governance | Approved target-skill release |

## Important Separation of Concerns

- SkillLens tells the project how to study and measure the lifecycle.
- SkillBrew keeps the internal knowledge collection compact and useful.
- SkillOpt optimizes the final procedural artifact under validation.
- Langfuse makes the nondeterministic operations observable.
- SME governance supplies authority that no model or framework can replace.

Using all approaches "to the fullest" means assigning each its strongest role.
It does not mean chaining three competing optimizers over the same text.

## Research Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Research benchmark results do not transfer to assessments | Establish project-specific baselines and ablations |
| LLM judge rewards persuasive wording | Require deterministic and downstream scores |
| One extractor creates biased evidence | Compare extractor configurations using extraction efficacy |
| Generic skill harms a target model | Measure target evolvability and negative transfer |
| Bank grows without bound | Apply Add/Rewrite/Remove and token budgets |
| SkillOpt overfits validation | Maintain immutable test split and temporal holdout |
| Learner difficulty is mistaken for assessment defect | Restrict, aggregate, and SME-review learner evidence |
| Observability becomes a second source of truth | Store authoritative immutable local artifacts |

