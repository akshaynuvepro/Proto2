# Conversation and Evidence Design

## Purpose

Conversations are source material, not optimization instructions. Before any
conversation can influence an assessment-improvement skill, it must be:

1. Normalized.
2. Classified by persona and assessment context.
3. Sanitized.
4. Converted into structured evidence.
5. Reviewed.
6. Assigned to a leakage-safe dataset split.

Raw conversational text never enters SkillOpt directly.

## Evidence Principles

- Preserve provenance from every extracted claim to exact source spans.
- Separate observed facts from extractor inferences.
- Prefer correction pairs and final artifacts over generic statements.
- Record uncertainty instead of forcing a conclusion.
- Do not treat repetition by one person as independent support.
- Do not mix learner assessment-comprehension problems with solution behavior.
- Keep approved evidence immutable; corrections create superseding versions.
- Use the minimum necessary text in downstream prompts.

## Canonical Conversation Record

### Field contract

| Field | Type | Required | Rule |
|---|---|---:|---|
| `schema_version` | string | Yes | Exact supported schema identifier |
| `conversation_id` | string | Yes | Stable, source-independent identifier |
| `source` | string | Yes | Source adapter name, such as `langsmith` |
| `source_conversation_id` | string | Yes | Original identifier |
| `source_uri` | string/null | No | Restricted source reference |
| `source_hash` | string | Yes | SHA-256 of canonical raw source |
| `persona` | enum | Yes | `sme`, `learner`, `mixed`, or `unknown` |
| `participant_ids` | string[] | Yes | Pseudonymous identifiers |
| `assessment_id` | string/null | No | Stable assessment identity |
| `assessment_version` | string/null | No | Source version when available |
| `target_skill_id` | string/null | No | Related assessment skill |
| `domain` | string/null | No | For example `aws` |
| `cohort_id` | string/null | No | Pseudonymous cohort |
| `started_at` | ISO timestamp | Yes | Original timezone retained in metadata |
| `ended_at` | ISO timestamp/null | No | Must not precede start |
| `messages` | message[] | Yes | Ordered canonical messages |
| `attachments` | attachment[] | Yes | Metadata only until separately approved |
| `consent` | object | Yes | Collection and processing permissions |
| `retention_class` | string | Yes | Organizational retention policy |
| `ingested_at` | ISO timestamp | Yes | Ingestion time |
| `normalizer_version` | string | Yes | Reproducibility |
| `metadata` | object | Yes | Source-specific, non-secret context |

### Message contract

| Field | Type | Required | Rule |
|---|---|---:|---|
| `message_id` | string | Yes | Stable within conversation |
| `sequence` | integer | Yes | Strictly increasing |
| `role` | enum | Yes | `system`, `user`, `assistant`, `tool` |
| `speaker_persona` | enum/null | No | `sme`, `learner`, `agent`, `system` |
| `timestamp` | ISO timestamp/null | No | Preserve missing timestamps explicitly |
| `content` | string | Yes | Canonical normalized text |
| `content_hash` | string | Yes | SHA-256 of canonical content |
| `source_message_id` | string/null | No | Original message identifier |
| `attachment_ids` | string[] | Yes | References only |
| `redaction_state` | enum | Yes | `raw`, `sanitized`, `quarantined` |

### Example

```json
{
  "schema_version": "assessment-conversation/1",
  "conversation_id": "conv_01J...",
  "source": "langsmith",
  "source_conversation_id": "thread-4821",
  "source_uri": null,
  "source_hash": "sha256:...",
  "persona": "sme",
  "participant_ids": ["person_7ac..."],
  "assessment_id": "assessment_aws_networking_01",
  "assessment_version": "draft-3",
  "target_skill_id": "aws-assessment-networking",
  "domain": "aws",
  "cohort_id": null,
  "started_at": "2026-08-07T09:00:00+05:30",
  "ended_at": "2026-08-07T09:27:00+05:30",
  "messages": [
    {
      "message_id": "msg_001",
      "sequence": 1,
      "role": "user",
      "speaker_persona": "sme",
      "timestamp": "2026-08-07T09:00:00+05:30",
      "content": "Create a scenario-based assessment for the supplied objective.",
      "content_hash": "sha256:...",
      "source_message_id": "source-msg-1",
      "attachment_ids": [],
      "redaction_state": "sanitized"
    }
  ],
  "attachments": [],
  "consent": {
    "assessment_improvement": true,
    "llm_processing": true,
    "telemetry_redacted": true
  },
  "retention_class": "assessment-research-approved",
  "ingested_at": "2026-08-07T10:00:00+05:30",
  "normalizer_version": "1.0.0",
  "metadata": {}
}
```

## Source Spans

Every extracted evidence field that asserts a source-backed claim uses one or
more source spans.

| Field | Type | Rule |
|---|---|---|
| `span_id` | string | Stable identifier |
| `conversation_id` | string | Parent conversation |
| `message_id` | string | Parent message |
| `start_char` | integer | Inclusive normalized-text offset |
| `end_char` | integer | Exclusive normalized-text offset |
| `text_hash` | string | Hash of selected text |
| `sanitized_excerpt` | string | Minimum text required for review |
| `redaction_labels` | string[] | Applied privacy/solution labels |

Source offsets refer to the normalized pre-redaction artifact. Sanitized
excerpts are used in routine review; authorized tools can resolve offsets to
raw text when policy allows.

## Persona Resolution

Persona resolution uses this precedence:

1. Trusted source metadata.
2. Explicit participant mapping supplied by the assessment platform.
3. Reviewed mapping rule for the source.
4. Classifier prediction with confidence.
5. `unknown`.

Classifier output alone cannot assign an authoritative SME identity. Low
confidence, mixed-persona, or conflicting records are quarantined for review.

## Sanitization

### Privacy labels

- `pii.direct`: name, email, phone, address, employee or learner number.
- `pii.quasi`: combination of attributes that may identify a participant.
- `secret.credential`: API keys, access tokens, passwords, connection strings.
- `internal.restricted`: protected assessment, customer, or infrastructure ID.
- `assessment.answer_key`: answer material not required by the current stage.
- `learner.solution`: learner solution content.
- `learner.solution_strategy`: procedural approach to solving.
- `learner.code`: submitted or discussed solution code.
- `learner.hint_request`: request for a hint or answer direction.

### Sanitization behavior

| Label | Stored in sanitized artifact | Sent to Langfuse | Sent to optimizer |
|---|---:|---:|---:|
| Direct PII | Placeholder | No | No |
| Quasi PII | Generalized or placeholder | No | Only if necessary |
| Credential | Placeholder | No | No |
| Restricted ID | Pseudonym | Pseudonym | Pseudonym |
| Answer key | Only approved evaluator copy | No by default | Only scorer, never learner extractor |
| Learner solution | No | No | No |
| Learner strategy | No | No | No |
| Learner code | No | No | No |
| Hint request | Intent label only | Intent label only | No content |

The redaction report stores labels, locations, policy version, model version,
confidence, and reviewer decision. It does not duplicate secret or solution
text.

## SME Evidence

### Evidence categories

- `assessment_brief`
- `learning_objective`
- `competency_coverage`
- `question_design_rule`
- `scenario_design_rule`
- `difficulty_rule`
- `distractor_rule`
- `scoring_rule`
- `answer_key_rule`
- `feedback_rule`
- `format_contract`
- `tool_workflow`
- `quality_constraint`
- `correction_pair`
- `accepted_choice`
- `rejected_choice`
- `exception`
- `positive_example`
- `negative_example`

### Field contract

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `evidence_id` | string | Yes | Immutable identity |
| `schema_version` | string | Yes | `sme-evidence/1` |
| `category` | enum | Yes | One category above |
| `claim` | string | Yes | Atomic reusable observation |
| `rationale` | string/null | No | Explicit SME reasoning |
| `failure_mechanism` | string/null | No | What bad behavior causes |
| `recommended_behavior` | string/null | No | What to do instead |
| `before` | object/null | No | Draft or rejected state |
| `after` | object/null | No | Accepted or final state |
| `positive_example` | string/null | No | Approved example |
| `negative_example` | string/null | No | Disapproved example |
| `applicability` | object | Yes | Domain, task, difficulty, and conditions |
| `exceptions` | string[] | Yes | When the claim must not apply |
| `source_spans` | span-ref[] | Yes | At least one |
| `extractor_confidence` | number | Yes | 0 through 1 |
| `inference_level` | enum | Yes | `explicit`, `strong_inference`, `weak_inference` |
| `review_status` | enum | Yes | Candidate lifecycle state |
| `supersedes` | string[] | Yes | Prior evidence IDs |
| `created_by` | object | Yes | Extractor model and prompt |
| `created_at` | timestamp | Yes | Creation time |

### Example

```json
{
  "evidence_id": "sme_ev_01J...",
  "schema_version": "sme-evidence/1",
  "category": "correction_pair",
  "claim": "Require an observable troubleshooting action instead of asking only for a definition.",
  "rationale": "The objective measures applied diagnosis, not recall.",
  "failure_mechanism": "Definition-only questions can pass learners who cannot perform the target task.",
  "recommended_behavior": "Place the learner in a constrained scenario and require evidence from an observable diagnostic step.",
  "before": {
    "summary": "Recall-only question"
  },
  "after": {
    "summary": "Scenario with a diagnostic decision and observable evidence"
  },
  "positive_example": null,
  "negative_example": null,
  "applicability": {
    "domains": ["aws"],
    "assessment_types": ["scenario"],
    "difficulty": ["intermediate", "advanced"]
  },
  "exceptions": [
    "A recall objective explicitly approved in the assessment blueprint"
  ],
  "source_spans": [
    {
      "span_id": "span_01J...",
      "text_hash": "sha256:..."
    }
  ],
  "extractor_confidence": 0.94,
  "inference_level": "explicit",
  "review_status": "pending",
  "supersedes": [],
  "created_by": {
    "prompt": "sme-evidence-extractor",
    "prompt_version": "git:...",
    "model": "configured-extractor"
  },
  "created_at": "2026-08-07T10:10:00+05:30"
}
```

### SME extraction procedure

1. Segment the conversation by assessment task or decision episode.
2. Locate final artifacts and explicit accept/reject statements.
3. Align drafts with corrected or final forms.
4. Extract atomic decisions instead of one broad summary.
5. Separate what changed from why it changed.
6. Identify applicability and exceptions.
7. Label explicit statements separately from inferences.
8. Link every field to source spans.
9. Detect conflicts with already approved evidence.
10. Emit candidates without mutating approved evidence.

### Maximizing SME conversation value

The extractor should exploit:

- The initial request as assessment intent.
- Agent drafts as examples of attempted behavior.
- SME corrections as preference labels.
- Rejected alternatives as high-risk or low-quality patterns.
- Iterative refinements as priority evidence.
- Final accepted output as a positive anchor.
- SME questions as indicators that the skill should ask for missing input.
- Repeated decisions across conversations as generalizable principles.
- One-off exceptions as bounded applicability, not universal rules.
- Tool use and validation actions as executable workflow evidence.

## Learner-Comprehension Evidence

### Allowed categories

- `instruction_ambiguity`
- `undefined_terminology`
- `expected_output_unclear`
- `assessment_scope_unclear`
- `environment_or_tool_confusion`
- `navigation_confusion`
- `prerequisite_not_communicated`
- `feedback_unclear`
- `conflicting_requirements`
- `example_or_format_mismatch`

### Excluded categories

- Requests for the answer.
- Requests for hints or next steps toward the answer.
- Solution attempts.
- Correct or incorrect technical reasoning.
- Submitted code or commands.
- Answer-key discussion.
- Score optimization strategies.
- Discussions that only reveal a knowledge gap in the tested subject.

A learner not knowing the subject matter is not automatically an assessment
clarity defect.

### Span classification

Each candidate span receives:

- `assessment_understanding`
- `solution_seeking`
- `mixed`
- `irrelevant`

Rules:

- `assessment_understanding` may proceed to structured extraction.
- `solution_seeking` is excluded and recorded by label only.
- `mixed` is redacted and sent to human review; it cannot enter aggregation
  automatically.
- `irrelevant` is ignored.

### Field contract

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `evidence_id` | string | Yes | Immutable identity |
| `schema_version` | string | Yes | `learner-confusion/1` |
| `category` | enum | Yes | Allowed category |
| `assessment_element_id` | string/null | No | Question, instruction, feedback, or environment |
| `confusion_statement` | string | Yes | Sanitized description |
| `observable_signal` | string | Yes | What the learner did or asked |
| `likely_cause` | string/null | No | Reviewer-confirmed or inferred |
| `proposed_clarity_need` | string/null | No | Not a solution |
| `severity` | enum | Yes | `low`, `medium`, `high`, `blocking` |
| `solution_content_detected` | boolean | Yes | Must be false for admission |
| `source_spans` | span-ref[] | Yes | Sanitized references |
| `learner_pseudonym` | string | Yes | Used only for distinct-support count |
| `cluster_id` | string/null | No | Assigned during aggregation |
| `extractor_confidence` | number | Yes | 0 through 1 |
| `review_status` | enum | Yes | Candidate lifecycle |
| `created_by` | object | Yes | Model and prompt lineage |

### Example

```json
{
  "evidence_id": "learner_ev_01J...",
  "schema_version": "learner-confusion/1",
  "category": "expected_output_unclear",
  "assessment_element_id": "instruction-block-2",
  "confusion_statement": "The required evidence format is not stated.",
  "observable_signal": "The learner asked whether a screenshot, command output, or written explanation was required.",
  "likely_cause": "The instruction asks for evidence without defining an accepted representation.",
  "proposed_clarity_need": "State the accepted evidence representations without describing how to obtain the answer.",
  "severity": "blocking",
  "solution_content_detected": false,
  "source_spans": [
    {
      "span_id": "span_01J...",
      "text_hash": "sha256:..."
    }
  ],
  "learner_pseudonym": "learner_83f...",
  "cluster_id": null,
  "extractor_confidence": 0.91,
  "review_status": "pending",
  "created_by": {
    "prompt": "learner-comprehension-classifier",
    "prompt_version": "git:...",
    "model": "configured-extractor"
  }
}
```

## Learner Aggregation

### Cluster key

Candidate evidence is clustered using:

- Assessment and version.
- Assessment element.
- Allowed confusion category.
- Semantic similarity of the sanitized confusion statement.
- Time window and cohort where relevant.

### Admission threshold

The default recurring-signal threshold is:

- At least three distinct learner pseudonyms.
- No solution-bearing member.
- Consistent category and assessment element.
- No evidence that the issue was already fixed in the current version.
- SME approval of the aggregate.

A single blocking event can be escalated for immediate review. It does not
become optimization evidence without approval.

### Aggregate record

```json
{
  "cluster_id": "confusion_cluster_01J...",
  "assessment_id": "assessment_aws_networking_01",
  "assessment_version": "v3",
  "assessment_element_id": "instruction-block-2",
  "category": "expected_output_unclear",
  "summary": "Learners cannot determine the required evidence representation.",
  "distinct_learner_count": 5,
  "event_count": 7,
  "severity_distribution": {
    "low": 0,
    "medium": 2,
    "high": 3,
    "blocking": 2
  },
  "evidence_ids": ["learner_ev_1", "learner_ev_2", "learner_ev_3"],
  "solution_leakage_check": "passed",
  "review_status": "pending"
}
```

## Evidence Review

### Review states

- `pending`
- `approved`
- `approved_with_edits`
- `rejected`
- `duplicate`
- `deferred`
- `superseded`

### Review record

| Field | Required | Meaning |
|---|---:|---|
| `review_id` | Yes | Immutable review event |
| `evidence_id` | Yes | Reviewed evidence |
| `decision` | Yes | One review state |
| `reviewer_id` | Yes | Authorized pseudonymous identity |
| `reviewer_role` | Yes | SME or designated reviewer |
| `reason_codes` | Yes | Structured explanation |
| `comment` | No | Sanitized review note |
| `field_corrections` | Yes | JSON merge-patch or empty object |
| `reviewed_at` | Yes | Timestamp |
| `policy_version` | Yes | Applied review policy |
| `langfuse_trace_id` | No | Review-preparation trace |

### Review checks

The reviewer confirms:

- The evidence reflects the source.
- The claim is atomic and actionable.
- Applicability is not overgeneralized.
- Exceptions are preserved.
- The evidence is not merely stylistic preference unless style is contractual.
- Learner evidence concerns understanding, not solving.
- No prohibited content remains.
- The proposed evidence does not contradict a protected policy.
- The evidence is suitable for training, validation, test, or observation only.

## Conflicts and Supersession

Evidence conflicts when two approved records recommend incompatible behavior
under overlapping applicability.

Conflict resolution produces one of:

- Narrow the applicability of both records.
- Define explicit precedence.
- Supersede one record.
- Create a domain-profile exception.
- Mark the conflict unresolved and exclude both from compilation.

Approved evidence is never edited in place. A corrected record references the
prior ID through `supersedes`.

## Dataset Splitting

### Leakage unit

All artifacts derived from the same assessment family, conversation thread,
SME correction chain, learner cluster, or near-duplicate assessment brief must
remain in one split.

### Recommended split strategy

- Split by assessment family first.
- Separate target-skill versions where possible.
- Use time-based holdout for the final test set.
- Preserve domain and difficulty coverage in every usable split.
- Keep the final test set inaccessible to distillation, bank curation, prompt
  tuning, and SkillOpt reflection.

### Split roles

| Split | Use |
|---|---|
| Support/train | Distill principles and optimize the improvement skill |
| Query/validation | Select bank proposals and SkillOpt candidates |
| Test | One-time release-candidate evaluation |
| Observation | Unapproved or low-confidence material excluded from scoring |

## Evidence Bundle

A run consumes one immutable evidence bundle.

```json
{
  "schema_version": "assessment-evidence-bundle/1",
  "bundle_id": "bundle_01J...",
  "created_at": "2026-08-07T12:00:00+05:30",
  "cutoff_at": "2026-08-07T00:00:00+05:30",
  "domain_profile_id": "aws-profile-v1",
  "target_scope": ["aws-assessment-*"],
  "sme_evidence_ids": ["sme_ev_1", "sme_ev_2"],
  "learner_cluster_ids": ["confusion_cluster_1"],
  "excluded_evidence": [
    {
      "evidence_id": "learner_ev_x",
      "reason": "solution_seeking"
    }
  ],
  "split_manifest": "artifact:split-manifest:...",
  "review_manifest": "artifact:review-manifest:...",
  "statistics": {
    "sme_positive_anchors": 12,
    "sme_correction_pairs": 18,
    "learner_confusion_clusters": 4,
    "distinct_smes": 3,
    "distinct_learners": 27
  },
  "content_hash": "sha256:..."
}
```

The bundle builder fails closed if evidence is unapproved, superseded,
solution-bearing, missing provenance, or assigned to an incompatible split.

## Quality Metrics

| Metric | Purpose |
|---|---|
| Persona accuracy | Prevent SME/learner contamination |
| Span grounding precision | Ensure evidence maps to source |
| SME evidence acceptance rate | Evaluate extractor usefulness |
| SME correction-pair completeness | Measure adaptation signal captured |
| Learner solution false-negative rate | Enforce safety boundary |
| Learner comprehension precision | Avoid treating knowledge gaps as assessment defects |
| Duplicate rate | Control redundant evidence |
| Conflict rate | Surface unstable policy |
| Reviewer correction rate | Calibrate extractor confidence |
| Split leakage count | Must remain zero |

Extractor models and prompts are promoted only after evaluation on a
human-labeled evidence set. A stronger general-purpose model is not assumed to
be a better evidence extractor.

