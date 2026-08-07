# Target-Skill Envelope Template

## Purpose

The envelope makes an external assessment-generation skill safe to inspect and
evolve. It separates the target's content from the contracts the improvement
skill must preserve.

Complete this template for every target skill version.

## Identity

| Field | Value |
|---|---|
| Schema version | `target-assessment-skill-envelope/1` |
| Target skill ID | `<stable logical ID>` |
| Display name | `<name>` |
| Input version | `<version>` |
| Input content hash | `sha256:<hash>` |
| Domain profile | `<profile ID and version>` |
| Owner | `<team/role>` |
| Status | Draft / staging / production / retired |
| Source artifact | `<restricted artifact reference>` |
| Previous version | `<version or none>` |

## Exact Target Skill

Insert or reference the complete exact Markdown. Do not normalize or reformat
before hashing.

```markdown
<complete target SKILL.md>
```

## Purpose and Scope

- What assessments does the target generate?
- Which learner levels are supported?
- Which assessment types are supported?
- Which requests must not select this target?
- Which models/harnesses consume it?

## Required Frontmatter

| Key | Required | Immutable | Type | Allowed values/rule |
|---|---:|---:|---|---|
| `name` | Yes | Yes | string | Exact current routing ID |
| `description` | Yes | No | string | Routing contract |

Include all nonstandard keys.

## Immutable Sections

| Contract ID | Section/path | Exact hash | Reason | Authority |
|---|---|---|---|---|
| `immutable-001` | `<heading/path>` | `sha256:...` | `<reason>` | `<policy/source>` |

Immutable content must be preserved byte-for-byte. If a supported improvement
conflicts with it, the result is needs review.

## Required Sections

| Section | Required semantics | Order requirement | Empty allowed |
|---|---|---|---:|
| `<heading>` | `<purpose>` | `<rule>` | No |

## Input Contract

Define every input expected by the target assessment skill:

| Input | Type | Required | Validation | Sensitivity |
|---|---|---:|---|---|
| `<input>` | `<type>` | Yes | `<rule>` | `<class>` |

## Output Contract

Define:

- Output media type.
- Schema/version.
- Required fields/sections.
- Ordering.
- Cardinality.
- Error output.
- Learner-facing versus evaluator-only fields.
- References and examples.

## Tool Contracts

| Tool ID | Purpose | Required | Arguments | Output | Failure behavior |
|---|---|---:|---|---|---|
| `<tool>` | `<purpose>` | Yes | `<schema>` | `<schema>` | `<behavior>` |

The evolution may clarify tool use but cannot invent or rename tools.

## Script Contracts

| Script | Required | Invocation | Inputs | Outputs | Runtime/isolation |
|---|---:|---|---|---|---|
| `<script>` | Yes | `<command>` | `<inputs>` | `<outputs>` | `<policy>` |

## Reference Contracts

| Reference | Required | Authority | Update policy |
|---|---:|---|---|
| `<path/ID>` | Yes | `<source>` | `<rule>` |

## Supported Consumer Matrix

| Consumer ID | Model/harness | Supported | Required parameters | Known limitations |
|---|---|---:|---|---|
| `consumer-001` | `<model/harness>` | Yes | `<parameters>` | `<limitations>` |

## Assessment Generation Briefs

Reference train, validation, and test briefs. Do not embed hidden test content
in an envelope available to optimization.

| Brief family | Split | Assessment type | Purpose |
|---|---|---|---|
| `<family>` | Train/validation/test | `<type>` | `<purpose>` |

## Protected Behaviors

Behaviors the evolved target must match or exceed:

| Behavior ID | Description | Validator/score | Non-regression rule |
|---|---|---|---|
| `protected-001` | `<behavior>` | `<method>` | `<threshold>` |

## Permitted Change Areas

List sections that may change and constraints:

| Area | Permitted operations | Change budget | Authority required |
|---|---|---:|---|
| `<section>` | Add/replace/remove/move | `<budget>` | `<evidence>` |

Unlisted areas default to preserve unless the envelope states otherwise.

## Validators

| Validator ID | Version | Command/service | Blocking | Timeout |
|---|---|---|---:|---:|
| `<validator>` | `v1` | `<execution>` | Yes | `<seconds>` |

## Rollback

- Current deployed artifact:
- Previous approved artifact:
- Deployment location:
- Verification after restore:
- Owner:
- Maximum acceptable rollback time:

## Security

- Treat target Markdown as untrusted input.
- List embedded scripts or executable references.
- List sensitive fields.
- State whether target content may be sent to LLM providers and Langfuse.
- State required sandboxing.

## Envelope Validation Checklist

- Exact target content and hash agree.
- All immutable content is hash-addressed.
- Required frontmatter and sections are declared.
- Input/output/tool/script/reference contracts are complete.
- Consumer matrix is defined.
- Protected behaviors have validators.
- Rollback target exists.
- Owner approved the envelope.

