# Principle Bank and SkillOpt Design

## Purpose

This document specifies how approved conversation evidence becomes one
validated assessment-improvement skill.

The process has two distinct optimization stages:

1. A SkillBrew-inspired curator selects the right improvement knowledge.
2. SkillOpt optimizes how that knowledge is expressed and executed as one
   deployable skill.

The two stages must remain separate. The principle bank is a knowledge and
coverage artifact. The SkillOpt output is a procedural runtime artifact.

## Inputs

A curation and optimization run requires:

- An immutable approved evidence bundle.
- The currently selected principle-bank version, or an empty bank.
- The seed improvement-skill template.
- One or more domain profiles.
- Target-skill fixtures or real target-skill envelopes.
- Train, validation, and test split manifests.
- Assessment briefs and expected behaviors.
- Deterministic validators and scoring configuration.
- Target, optimizer, extractor, and judge model configuration.
- Token, cost, concurrency, retry, and time budgets.

The run refuses to start if the evidence bundle contains unapproved evidence,
missing source spans, unresolved conflicts marked blocking, or learner solution
content.

## Assessment Improvement Principle

### Field contract

| Field | Type | Required | Rule |
|---|---|---:|---|
| `schema_version` | string | Yes | `assessment-principle/1` |
| `principle_id` | string | Yes | Stable logical identity |
| `version` | integer | Yes | Starts at 1 and increases |
| `parent_version_id` | string/null | Yes | Set for rewrites |
| `title` | string | Yes | Short, unique within bank |
| `principle` | string | Yes | Imperative, executable rule |
| `when_to_apply` | string[] | Yes | Observable conditions |
| `when_not_to_apply` | string[] | Yes | Boundaries |
| `failure_mechanism` | string | Yes | Why the current process fails |
| `remedy` | string[] | Yes | Concrete ordered actions |
| `high_risk_blacklist` | string[] | Yes | Harmful actions to avoid |
| `validation_expectations` | string[] | Yes | Observable proof |
| `positive_example_ids` | string[] | Yes | Approved evidence |
| `negative_example_ids` | string[] | Yes | Approved correction/failure evidence |
| `learner_cluster_ids` | string[] | Yes | Approved comprehension clusters |
| `assessment_types` | string[] | Yes | Applicable forms |
| `domains` | string[] | Yes | Empty means generic |
| `target_capabilities` | string[] | Yes | Required consumer abilities |
| `confidence` | number | Yes | 0 through 1 |
| `review_status` | enum | Yes | Pending, approved, rejected, superseded |
| `utility_history` | object[] | Yes | Evaluation results |
| `coverage_clusters` | string[] | Yes | Distribution coverage |
| `redundancy_links` | object[] | Yes | Similar principle IDs and scores |
| `contradiction_links` | object[] | Yes | Conflicting IDs and disposition |
| `created_at` | timestamp | Yes | Immutable |
| `content_hash` | string | Yes | SHA-256 |

### Valid example

```json
{
  "schema_version": "assessment-principle/1",
  "principle_id": "prn_instruction_observable_outcome",
  "version": 2,
  "parent_version_id": "prn_instruction_observable_outcome:v1",
  "title": "State observable completion outcomes",
  "principle": "Write task instructions so the learner can identify the required end state without being told the solution path.",
  "when_to_apply": [
    "The assessment requires a produced artifact or configured environment",
    "Learners repeatedly ask what counts as complete"
  ],
  "when_not_to_apply": [
    "The outcome itself is intentionally the discovery target"
  ],
  "failure_mechanism": "The instruction describes activity but not the observable artifact or state used for evaluation.",
  "remedy": [
    "Name the artifact or observable state",
    "State externally verifiable acceptance criteria",
    "Do not prescribe the implementation sequence"
  ],
  "high_risk_blacklist": [
    "Do not include commands that solve the task",
    "Do not expose evaluator secrets"
  ],
  "validation_expectations": [
    "A learner can restate the expected output",
    "No answer-bearing sequence appears"
  ],
  "positive_example_ids": ["sme_ev_104"],
  "negative_example_ids": ["sme_ev_077"],
  "learner_cluster_ids": ["cluster_012"],
  "assessment_types": ["hands-on"],
  "domains": [],
  "target_capabilities": ["structured-instruction-editing"],
  "confidence": 0.92,
  "review_status": "approved",
  "utility_history": [],
  "coverage_clusters": ["instruction-completion-state"],
  "redundancy_links": [],
  "contradiction_links": [],
  "created_at": "2026-08-07T12:00:00+05:30",
  "content_hash": "sha256:..."
}
```

### Rejected principle examples

- "Make the assessment good." It is not actionable or measurable.
- "Give learners commands when they struggle." It crosses the solution
  boundary.
- "Always reduce difficulty after a complaint." It ignores assessment intent
  and aggregate evidence.
- "Use AWS service X." It invents domain content without a domain profile.

## Principle Distillation

### Candidate generation

Candidate generation processes approved evidence in bounded groups:

1. Group evidence by assessment type, decision category, failure mechanism,
   domain scope, and learner-confusion cluster.
2. Provide both successful anchors and correction/failure evidence.
3. Ask the distiller to identify reusable mechanisms, not summaries.
4. Require source evidence IDs for every claim.
5. Require applicability, non-applicability, remedy, blacklist, and validation.
6. Validate citations and schema deterministically.
7. Reject candidates whose only contribution is formatting or vague advice.

### Hierarchical merge

When evidence volume is large:

1. Distill per trajectory or small evidence group.
2. Merge within one failure-mechanism cluster.
3. Merge within one assessment type.
4. Compare across domains to identify generic versus profile-specific rules.
5. Preserve minority or conflicting rules as explicit alternatives.

The merge stage may consolidate wording but cannot create unsupported policy.

## Bank-Curation Lifecycle

### Current bank analysis

For each principle, the diagnoser produces:

- Keep, Rewrite, or Remove verdict.
- Evidence supporting the verdict.
- Positive and negative utility observations.
- Coverage contribution.
- Redundancy and contradiction analysis.
- Staleness assessment.
- Proposed rewrite when applicable.

### Add candidates

Add candidates come from:

- Approved evidence clusters with no matching principle.
- Downstream failures not explained by existing principles.
- Target-consumer failures revealing missing execution guidance.
- Repeated learner-comprehension clusters approved by an SME.
- New protected contracts in a domain profile.

### Proposal construction

The planner produces multiple coherent bank candidates rather than one answer:

- Conservative candidate: minimal verified edits.
- Coverage candidate: adds supported uncovered behavior.
- Consolidation candidate: rewrites/removes redundancy.
- Safety candidate: strengthens failure boundaries and blacklists.

Candidate philosophies are metadata, not scoring preferences.

### Verification objectives

Let:

- `U(B)` be downstream utility of bank `B`.
- `D(B)` be diversity or non-redundancy.
- `C(B)` be approved distribution coverage.
- `R(B)` be risk penalty.
- `T(B)` be compiled token cost.

The current bank is `B0`. A candidate is eligible only if:

```text
U(Bcandidate) >= U(B0) - configured_non_regression_tolerance
all hard safety and compatibility gates pass
```

For release-oriented selection, the default tolerance is zero. For exploratory
analysis, a nonzero tolerance may be recorded but cannot produce a release.

Eligible candidates are compared on:

```text
maximize U, D, C
minimize R, T
```

Selection retains the Pareto frontier and applies this deterministic tie-break:

1. Higher held-out utility.
2. Lower negative-transfer count.
3. Higher approved evidence coverage.
4. Lower contradiction penalty.
5. Lower compiled token count.
6. Lexicographically smaller candidate ID for reproducibility.

### Utility measurement

Bank utility is not an LLM opinion about principles. It is measured by
compiling each candidate bank into an improvement skill and running a bounded
validation subset through the downstream rollout.

### Diversity measurement

Use both lexical and embedding similarity over title, principle,
failure mechanism, and applicability. Flag pairs above configured thresholds
for consolidation. Human-defined "must coexist" links override automatic
redundancy removal.

### Coverage measurement

Coverage is calculated across:

- Approved SME decision clusters.
- Approved learner-comprehension clusters.
- Assessment types.
- Difficulty levels.
- Target-skill structures.
- Target consumer models.
- Domains and profiles.

A principle covers a cluster only when its applicability and evidence links
match; keyword overlap alone is insufficient.

## Bank Version Contract

A bank version records:

```json
{
  "schema_version": "assessment-principle-bank/1",
  "bank_id": "bank_01J...",
  "version": 4,
  "parent_bank_version": "bank_01J...:v3",
  "principle_versions": [
    "prn_instruction_observable_outcome:v2"
  ],
  "evidence_bundle_id": "bundle_01J...",
  "proposal_id": "proposal_consolidation_02",
  "objectives": {
    "utility": 0.81,
    "diversity": 0.76,
    "coverage": 0.88,
    "risk_penalty": 0.0,
    "compiled_tokens": 1420
  },
  "hard_gates_passed": true,
  "pareto_status": "selected",
  "created_at": "2026-08-07T12:00:00+05:30",
  "content_hash": "sha256:..."
}
```

## Improvement-Skill Compiler

### Inputs

- Selected bank version.
- Seed template version.
- Mandatory organization policies.
- Generic target-skill contract.
- Compiler configuration and token budget.

### Output

- Compiled `SKILL.md` seed.
- Compilation manifest.
- Included and excluded principle versions.
- Consolidation map.
- Token count.
- Lint and structure results.

### Compiler rules

- Preserve mandatory sections and order.
- Prefer executable procedures over background explanation.
- Consolidate duplicate remedies.
- Retain explicit learner-solution prohibitions.
- Retain compatibility-preservation rules.
- Retain no-change and needs-review behaviors.
- Do not embed domain facts.
- Do not silently omit a high-risk blacklist.
- Fail if required principles cannot fit the release token budget.

## Benchmark Item Contract

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Stable item identity |
| `split` | enum | Train, validation, or test |
| `split_group` | string | Leakage boundary |
| `target_skill_envelope` | object/ref | Current target skill and contracts |
| `domain_profile` | object/ref | Domain constraints |
| `assessment_brief` | object | Downstream generation request |
| `evidence_bundle` | object/ref | Approved evidence visible to evolution |
| `expected_behaviors` | object[] | SME-approved rubric |
| `protected_behaviors` | object[] | Must not regress |
| `deterministic_validators` | string[] | Validator identifiers |
| `consumer_config` | object | Model/harness parameters |
| `expected_output` | object/null | Optional gold target/evaluation data |
| `metadata` | object | Assessment type, level, and cohort |

Target skill, profile, and evidence are delimited as untrusted data in prompts.
Benchmark items never contain raw learner conversations.

## Custom SkillOpt Environment

### Data loader

The loader:

- Reads versioned split directories.
- Validates each item and referenced artifact hash.
- Enforces split-group isolation.
- Supports deterministic sampling by seed.
- Reports distribution statistics.
- Rejects near-duplicate leakage.
- Does not expose final test items during training.

### Rollout helper

For each item and candidate improvement skill:

1. Validate and load all referenced artifacts.
2. Run the target-skill evolution call.
3. Parse the full evolved skill and structured patch.
4. Apply deterministic evolution hard gates.
5. Run the original target skill on the assessment brief.
6. Run the evolved target skill under paired configuration.
7. Validate both generated assessments.
8. Score protected and improvement dimensions.
9. Persist all prompts, outputs, patches, assessments, and scores.
10. Persist a role-tagged conversation trajectory for SkillOpt reflection.
11. Return hard, soft, and detailed extras.

If evolution hard gates fail, downstream generation may be skipped to control
cost, but the failed trajectory must still be persisted.

### Environment adapter

The adapter supplies:

- `build_train_env`
- `build_eval_env`
- `build_env_from_batch`
- `rollout`
- `get_task_types`

It uses SkillOpt public extension points and does not patch optimizer internals.

### Trajectory shape

The reflection trajectory contains:

1. Candidate improvement skill as the system instruction.
2. Evolution task as a user message.
3. Evolved target result as an assistant message.
4. Deterministic validation feedback.
5. Original and evolved assessment generation results.
6. Detailed hard and soft score feedback.

Large artifacts may be summarized in the trajectory only when stable artifact
references and hashes are also provided.

## Evolution Hard Gates

All gates must pass:

- Evolution output schema valid.
- Complete evolved skill present for update decisions.
- Structured patch applies cleanly and reconstructs the evolved skill.
- Required frontmatter preserved.
- Immutable sections unchanged.
- Required sections and tool contracts present.
- Output contracts preserved unless authoritative evidence permits change.
- Every material patch operation has approved evidence IDs.
- No unsupported domain claim introduced.
- No raw learner or solution content present.
- No prompt-injection instruction from target data executed.
- All configured target validators pass.

## Downstream Assessment Hard Gates

- Required assessment schema valid.
- Questions and expected responses are internally consistent.
- Answer keys or evaluator criteria are technically correct where verifiable.
- No secrets or evaluator-only data leak.
- Assessment count, types, duration, and constraints match the brief.
- Protected competency and difficulty requirements remain satisfied.
- Learner-facing content contains no unintended solution.

## Soft Scores

Default soft dimensions are normalized to 0 through 1:

| Score | Meaning |
|---|---|
| SME adaptation | Reproduces approved SME decisions and rationale |
| Assessment utility | Overall downstream assessment quality |
| Objective coverage | Covers required competencies and blueprint |
| Difficulty calibration | Matches intended cognitive and practical level |
| Scenario realism | Resembles authentic work without irrelevant complexity |
| Instruction clarity | Makes task and completion state understandable |
| Learner-confusion response | Resolves approved comprehension issues |
| Minimality | Changes only what evidence requires |
| Maintainability | Produces a coherent, usable target skill |
| Target compatibility | Works for the configured consumer |
| Evidence grounding | Strength and relevance of cited evidence |

Weights are configuration, recorded with every score. The initial recommended
weighting gives SME adaptation and downstream assessment utility the largest
share. A weight change creates a new evaluation-profile version.

### Reward mapping

The SkillOpt result includes:

- `hard`: 1 only when all critical gates pass.
- `soft`: weighted normalized score.
- `baseline_soft`: original target's paired score.
- `delta_soft`: candidate minus baseline.
- `extras`: per-dimension values, failure reasons, artifact IDs, and
  trace IDs.

Validation selection uses delta and protected-dimension non-regression, not
candidate score alone.

## Baseline and Consumer Matrix

Every candidate is compared with:

- No improvement skill.
- Seed improvement skill.
- Current best improvement skill.

Consumers include each supported assessment-generator model/harness and each
target-skill fixture family. Report:

- Mean and confidence interval where repetitions exist.
- Per-item delta.
- Per-consumer delta.
- Negative-transfer count and rate.
- Hard-gate pass rate.
- Cost and latency.

## Initial Data Without AWS Skills

Until real AWS skills arrive:

- Create structurally diverse, domain-neutral target fixtures.
- Label fixtures synthetic.
- Use placeholder domain facts, never invented AWS claims.
- Test frontmatter, required sections, references, scripts, tool contracts, and
  output-contract preservation.
- Do not claim domain correctness or production readiness.

When real AWS skills arrive, ingest them through target envelopes and create a
new dataset version. Synthetic results remain engineering tests only.

## Initial Data Without Learner Conversations

- Use an empty learner evidence list.
- Keep learner-related schemas and validators active.
- Mark learner-comprehension metrics not evaluated.
- Do not fabricate learner evidence for optimization.
- Use synthetic learner snippets only in classifier/redaction unit tests and
  label them synthetic.

## Configuration Example

```yaml
env:
  name: assessment_improver
  skill_init: templates/assessment-skill-improver/SKILL.md
  split_dir: data/assessment_improver_split
  workers: 4
  max_completion_tokens: 8192

train:
  num_epochs: 4
  batch_size: 16

gradient:
  minibatch_size: 8
  merge_batch_size: 8

optimizer:
  learning_rate: 4

assessment_improver:
  evaluation_profile: assessment-quality-v1
  hard_gate_profile: release-gates-v1
  persist_intermediate_artifacts: true
  compare_with_original_target: true
  require_evidence_citations: true
  learner_solution_leakage_tolerance: 0
```

Actual defaults must be calibrated with a small dry run before a full training
budget is approved.

## Reproducibility Requirements

Every result records:

- SkillOpt version and repository revision.
- Proto2 revision.
- Model provider, model, and parameters.
- Prompt names, Git hashes, and Langfuse versions.
- Dataset and artifact hashes.
- Split seed and sampling decisions.
- Evaluation profile and validator versions.
- Environment and dependency lock.
- Retry and failure history.
- Token and cost totals.

## Acceptance Criteria

- Selected principles are approved and evidence-backed.
- Bank selection preserves utility and improves at least one required
  objective.
- The compiled seed is reproducible.
- SkillOpt can train, resume, and produce a best skill.
- Every reflected result has a nonempty trajectory.
- Test data is never used for reflection or selection.
- The best skill improves held-out downstream delta without protected
  regressions.
- Negative transfer is explicitly reported for every supported consumer.

