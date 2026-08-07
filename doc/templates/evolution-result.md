# Evolution Result Template

## Purpose

This is the human-readable companion to the structured evolution-result JSON.
It must be generated from the same immutable artifacts and must not introduce
new claims.

## Result Identity

| Field | Value |
|---|---|
| Schema version | `assessment-skill-evolution-result/1` |
| Evolution ID | `<ID>` |
| Run ID | `<ID>` |
| Decision | Update / no change / needs review |
| Created at | `<timestamp>` |
| Improvement skill | `<version and hash>` |
| Principle bank | `<version and hash>` |
| Evidence bundle | `<ID and hash>` |
| Domain profile | `<ID and hash>` |
| Evaluation profile | `<ID and version>` |
| Langfuse trace | `<safe URL/ID>` |

## Target Identity

| Field | Original | Proposed |
|---|---|---|
| Skill ID | `<ID>` | Same |
| Version | `<version>` | `<proposed version>` |
| Content hash | `sha256:...` | `sha256:...` |
| Deployment status | `<status>` | Proposal only |

## Executive Summary

State:

- What evidence-backed problem was addressed.
- What changed or why no change is recommended.
- Downstream assessment result.
- Main risks and review focus.

## Complete Evolved Target Skill

Include the complete exact proposed Markdown for update decisions. Its hash
must match the structured result.

```markdown
<complete evolved target skill>
```

## Structured Change Summary

| Operation | Section | Change | Evidence | Expected effect | Risk |
|---|---|---|---|---|---|
| `op-001` | `<section>` | `<summary>` | `<IDs>` | `<effect>` | Low/medium/high |

Attach the exact machine-applicable patch artifact.

## Evidence Coverage

| Evidence ID | Type | Disposition | Operations | Reason |
|---|---|---|---|---|
| `<ID>` | SME/learner cluster/policy | Applied/already satisfied/not applicable/blocked/review | `<ops>` | `<reason>` |

Every evidence item in the input bundle must appear once.

## Contract Preservation

| Contract ID | Type | Result | Validator | Notes |
|---|---|---|---|---|
| `<ID>` | Frontmatter/section/tool/output/script | Preserved/authorized change/unverified | `<validator>` | `<notes>` |

## Learner-Clarity Actions

| Cluster | Problem | Change | Solution-boundary proof | SME approval |
|---|---|---|---|---|
| `<ID>` | `<comprehension issue>` | `<action>` | `<why no solution leaked>` | `<review ID>` |

Use not evaluated when no learner evidence exists.

## Hard-Gate Report

| Gate | Result | Validator/version | Artifact/trace | Failure |
|---|---:|---|---|---|
| Output schema | Pass/fail | `<ID>` | `<ref>` | `<reason>` |
| Patch reconstruction | Pass/fail | | | |
| Immutable preservation | Pass/fail | | | |
| Tool/output contracts | Pass/fail | | | |
| Evidence grounding | Pass/fail | | | |
| Domain grounding | Pass/fail | | | |
| Learner solution leakage | Pass/fail | | | |
| Assessment correctness | Pass/fail | | | |

Any failure makes the result ineligible for promotion.

## Downstream Assessment Comparison

| Dimension | Original | Candidate | Delta | Protected | Evaluation source |
|---|---:|---:|---:|---:|---|
| SME adaptation | | | | Yes/no | |
| Assessment utility | | | | | |
| Objective coverage | | | | | |
| Difficulty calibration | | | | | |
| Scenario realism | | | | | |
| Instruction clarity | | | | | |
| Learner-confusion response | N/E or score | | | | |
| Maintainability | | | | | |

Include per-item and per-consumer reports as linked artifacts.

## Consumer Matrix

| Target fixture/skill | Consumer | Baseline | Candidate | Delta | Hard pass | Negative transfer |
|---|---|---:|---:|---:|---:|---:|
| `<target>` | `<consumer>` | | | | | |

## Risks and Uncertainties

| Severity | Risk/uncertainty | Evidence | Mitigation | Review owner |
|---|---|---|---|---|
| Low/medium/high | `<description>` | `<refs>` | `<action>` | `<role>` |

## Intermediate Artifacts

Link:

- Input envelope.
- Domain profile.
- Evidence bundle.
- Principle and bank versions.
- Compilation manifest.
- SkillOpt step/candidate.
- Baseline and candidate assessments.
- Structured patch.
- Validator outputs.
- Score matrix.
- Langfuse traces and experiments.

## Recommended SME Review Focus

Provide a short ordered list based on risk and evaluator disagreement.

## Review Decision

| Field | Value |
|---|---|
| Reviewer | `<authorized identity>` |
| Decision | Approve / reject / request revision |
| Timestamp | `<timestamp>` |
| Comments | `<comments>` |
| Approval artifact | `<immutable event ID>` |

## Promotion and Rollback

Complete only after approval:

- Release ID:
- Deployment target:
- Previous version:
- Verification result:
- Rollback artifact:
- Promoted by:
- Promoted at:

The evolution result remains a proposal until these fields reference an
approved release event.
