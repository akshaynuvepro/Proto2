---
name: "aws-assessment-author"
description: "Authors complete Nuvepro AWS assessment repositories (_Main/_Solution/_Validation) in TLS house style."
version: "1"
domain: "aws"
content_type: "assessment"
template_id: "tpl_8d39372ac5e35b51ca64"
template_hash: "sha256:2cc02b6bf75f93236087ddf1e3ba92503dc534221f416115515176d73f9ef630"
---

# AWS Assessment Author Skill Package

## 🎯 Purpose

This skill package authors **complete, production-ready Nuvepro AWS assessments** as three repositories:

- **`<base>_Main`** — learner-facing task doc, starter code, images, config
- **`<base>_Solution`** — evaluator-only reference implementation
- **`<base>_Validation`** — evaluator-only grader (Python harness or JSON testcases)

The package enforces Nuvepro TLS house style, exact-name discipline, marks arithmetic, and the learner-safe vs. evaluator-only boundary.

---

## 🧠 When to Use This Skill

Use this skill when you need to:

- Author a **hands-on AWS assessment** (not a quiz or theory test)
- Generate all three repos in one pass
- Enforce exact resource naming, marks summation, and phase-testcase mapping
- Match TLS house style (YAML front-matter, emoji headers, concise structure)
- Ground output in the canonical worked example (Brokerage Trade Settlement Platform)

---

## 🔥 The Three Output Repositories

| Repository | Audience | Contents | Security Rule |
|------------|----------|----------|---------------|
| **`<base>_Main`** | Learner | Task doc (`Assessment-Activities.md`), starter code, images, CloudFormation templates, Dockerfiles, `buildspec.yml`, `appspec.yaml`, `taskdef.json`, Postman collections, config YAML | **Never** contains solution code, answer keys, or grader expected values |
| **`<base>_Solution`** | Evaluator only | Complete reference implementation with all methods filled, correct resource names, working integrations | Not visible to learners |
| **`<base>_Validation`** | Evaluator only | Python grader harness (`grader.py`, `testcases.py`, `utils.py`) or JSON testcases; checks exact resource names, API responses, DB state, CloudFormation outputs | Not visible to learners |

---

## 📐 Ordered Workflow

Follow this sequence when authoring an assessment:

1. **Read `DOMAIN_KNOWLEDGE.md`** — understand AWS services, common patterns, resource naming conventions (kebab-case 82.5%), top services (API Gateway, DynamoDB, ECS, Lambda, S3, KMS, CloudFormation).

2. **Read `STRUCTURE.md`** — understand the triplet structure, file layout, grader formats (prefer Python harness), phase-testcase mapping, marks rules.

3. **Read `TASK_DOC.md`** — learn the task doc schema (YAML front-matter, scenario, phases, tasks with inline marks, resource checklist, submission instructions).

4. **Read `GRADER.md`** — learn the Python harness pattern (boto3 clients, check functions, testcase registry, marks summation, exact-name checks).

5. **Read `WORKED_EXAMPLE.md`** — study the canonical Brokerage Trade Settlement Platform assessment (5 phases, 16 testcases, 100 marks, Python harness, CloudFormation + ECS + CodePipeline + KMS + CloudTrail).

6. **Author the assessment**:
   - Define scenario, services, duration, total marks, phases.
   - Write task doc with exact resource names.
   - Write starter code (empty methods, wired AWS SDK calls, Dockerfile, buildspec, appspec, taskdef, CloudFormation template).
   - Write solution code (complete implementation).
   - Write grader (Python harness with testcases matching phases and tasks).
   - Verify marks summation: `sum(testcase.marks) == total_marks`.
   - Verify every phase has ≥1 testcase.
   - Verify every testcase maps to a task.
   - Verify no solution code or expected values in `_Main`.

---

## ⚠️ Strict Rules (Do NOT Violate)

- **Exact-name discipline**: Resource names in the task doc MUST match, byte-for-byte, the names checked by the grader. No extra spaces, no case differences.
- **Marks arithmetic**: `sum(testcase.marks) == total_marks`. Every testcase has a positive mark. Every phase has ≥1 testcase.
- **Learner-safe boundary**: Never put solution code, answer keys, or grader expected values into `_Main`.
- **Phase-testcase mapping**: Every testcase belongs to a phase. Every phase has ≥1 testcase. Every testcase maps to a task in the task doc.
- **Real-world difficulty**: Hands-on debugging, decision-making, integration work. Not trivial MCQ or copy-paste.
- **House style**: YAML front-matter (name, description only), emoji headers, concise bullet points, no filler.
- **Grader format**: Prefer Python harness (boto3 clients, check functions, testcase registry). JSON testcases are acceptable but less flexible.
- **Starter code**: Must be incomplete (empty methods, TODOs) but structurally sound (compiles, has AWS SDK calls wired, has Dockerfile/buildspec/appspec/taskdef/CloudFormation template).

---

## 📌 Output Expectations

When you invoke this skill package, you will produce:

- **`<base>_Main/Assessment-Activities.md`** — task doc with YAML front-matter, scenario, phases, tasks (with inline marks), resource checklist, submission instructions.
- **`<base>_Main/<project>/`** — starter code (Java/Python/Node.js), Dockerfile, buildspec.yml, appspec.yaml, taskdef.json, CloudFormation template, Postman collection, images.
- **`<base>_Main/config.yaml`** — Nuvepro platform config (duration, marks, services).
- **`<base>_Solution/<project>/`** — complete reference implementation.
- **`<base>_Validation/grader.py`** — Python harness with boto3 clients, check functions, testcase registry, marks summation.
- **`<base>_Validation/testcases.py`** — testcase definitions (id, name, marks, category, phase, check function).
- **`<base>_Validation/utils.py`** — helper functions (resource existence checks, API calls, DynamoDB queries, CloudFormation output parsing).

---

## 🧠 Quality Check (Before Finalizing)

- [ ] YAML front-matter present in all `.md` files (name, description only).
- [ ] Emoji headers used consistently (🎯 Purpose, 🧠 Core Principles, 🔥 Difficulty Standard, ⚠️ Strict Rules, 📌 Output Expectations, 🧠 Quality Check).
- [ ] Concise, bullet-point structure. No filler paragraphs.
- [ ] Exact resource names stated in task doc and checked in grader (byte-for-byte match).
- [ ] `sum(testcase.marks) == total_marks`.
- [ ] Every phase has ≥1 testcase.
- [ ] Every testcase maps to a task in the task doc.
- [ ] No solution code, answer keys, or grader expected values in `_Main`.
- [ ] Starter code is incomplete but structurally sound (compiles, has AWS SDK calls, has Dockerfile/buildspec/appspec/taskdef/CloudFormation template).
- [ ] Grader is Python harness (boto3 clients, check functions, testcase registry).
- [ ] Real-world, hands-on difficulty (debugging, decision-making, integration).
- [ ] Matches TLS house style (senior-engineer tone, ready-to-use, minimal back-and-forth).

---

## 📂 Reference Files in This Package

| File | Purpose |
|------|---------|
| **`SKILL.md`** (this file) | Router/overview: what this authors, when to use it, ordered workflow, three repos, hard rules, pointers to other files. |
| **`DOMAIN_KNOWLEDGE.md`** | AWS services, resource naming conventions (kebab-case 82.5%), top services (API Gateway, DynamoDB, ECS, Lambda, S3, KMS, CloudFormation), testcase categories. |
| **`STRUCTURE.md`** | Triplet structure (`_Main`/`_Solution`/`_Validation`), file layout, grader formats (Python harness vs. JSON), phase-testcase mapping, marks rules, learner-safe vs. evaluator-only boundary. |
| **`TASK_DOC.md`** | Task doc schema (YAML front-matter, scenario, phases, tasks with inline marks, resource checklist, submission instructions), house style, exact-name discipline. |
| **`GRADER.md`** | Python harness pattern (boto3 clients, check functions, testcase registry, marks summation, exact-name checks), testcase schema, common check kinds (API, resource, DB, code, e2e). |
| **`WORKED_EXAMPLE.md`** | Canonical Brokerage Trade Settlement Platform assessment (5 phases, 16 testcases, 100 marks, Python harness, CloudFormation + ECS + CodePipeline + KMS + CloudTrail), annotated task doc, grader excerpts, starter code structure. |

---

## 🚀 Quick Start

1. Read `DOMAIN_KNOWLEDGE.md` to understand AWS patterns.
2. Read `STRUCTURE.md` to understand the triplet layout.
3. Read `TASK_DOC.md` to learn the task doc schema.
4. Read `GRADER.md` to learn the Python harness pattern.
5. Read `WORKED_EXAMPLE.md` to see a complete, annotated example.
6. Author your assessment following the ordered workflow above.
7. Run the quality check before finalizing.

---

## 🧠 Key Principles

- **Exact-name discipline**: Resource names in task doc = names in grader (byte-for-byte).
- **Marks arithmetic**: `sum(testcase.marks) == total_marks`.
- **Learner-safe boundary**: No solution code or expected values in `_Main`.
- **Real-world difficulty**: Hands-on debugging, decision-making, integration work.
- **House style**: YAML front-matter, emoji headers, concise bullet points, senior-engineer tone.
- **Grader format**: Prefer Python harness (boto3 clients, check functions, testcase registry).
- **Phase-testcase mapping**: Every testcase belongs to a phase, maps to a task, has a positive mark.

---

**End of `SKILL.md`**
