---
name: Testcase and Marks Schema
description: The structured testcase schema, the marks rule (sum == total), and the full task<->grader<->marks consistency contract for AWS assessments.
---

# Testcase and Marks Schema

## 🎯 Purpose

Define the **canonical testcase structure**, the **marks arithmetic rule**, and the **task-grader-marks consistency contract** that every AWS assessment must honor.

This file is the **single source of truth** for:
- Testcase field schema and grouping.
- The non-negotiable marks rule: `sum(testcase.marks) == total_marks`.
- The phase-task-testcase-grader alignment contract.

---

## 🧠 Core Principles

1. **Every testcase maps to a task** in the learner-facing task doc.
2. **Every phase has ≥ 1 testcase**; no orphan phases.
3. **Marks sum exactly to the declared total**; no rounding, no approximation.
4. **Resource names in the task doc match grader checks byte-for-byte** (case, hyphens, underscores).
5. **Grader expected values never appear in _Main**; they live only in _Validation.

---

## 📐 Testcase Schema

### Required Fields

| Field       | Type   | Description                                                                 |
|-------------|--------|-----------------------------------------------------------------------------|
| `id`        | string | Stable identifier, e.g. `TC001`, `tc01`, `testcase1`. Used in grader logs. |
| `name`      | string | Human-readable check title, e.g. `testcase1 cloudformation stack`.         |
| `marks`     | number | Positive number; all testcase marks sum to `total_marks`.                  |
| `category`  | string | Grouping tag (service or capability), e.g. `kms`, `api`, `cloudformation`. |
| `phase`     | string | The phase/milestone this check belongs to, matching task doc phase names.  |

### Optional/Format-Specific Fields

Depending on `check_kind` (api, resource, db, code, e2e), the testcase may include:

- **API checks**: `endpoint`, `method`, `expectedStatusCode`, `expectedFields`.
- **Resource checks**: `resourceType`, `resourceName`, `expectedProperties`.
- **Database checks**: `tableName`, `expectedRecords`, `encryptionValidation`.
- **Code checks**: `filePath`, `expectedPatterns`, `forbiddenPatterns`.
- **E2E checks**: `scenario`, `steps`, `expectedOutcome`.

---

## 🔢 Marks Rule (Non-Negotiable)

```
sum(testcase.marks for testcase in all_testcases) == total_marks
```

**Example:**

```json
{
  "total_marks": 100,
  "testcases": [
    {"id": "tc01", "marks": 8},
    {"id": "tc02", "marks": 6},
    ...
    {"id": "tc16", "marks": 3}
  ]
}
```

**Validation:**
```
8 + 6 + 8 + 6 + 10 + 8 + 6 + 6 + 8 + 8 + 8 + 4 + 4 + 4 + 3 + 3 = 100 ✓
```

**Common values:**
- `total_marks`: 100 (default), 54 (seen in corpus).
- Testcase count: 14–16 (median 14).

---

## 🗂️ Grouping and Phases

### Phase-Task-Testcase Alignment

Every testcase belongs to **exactly one phase**. The phase name in the testcase **must match** the phase name in the task doc.

**Example (from canonical worked example):**

| Phase                                      | Tasks (from task doc)                                                                 | Testcases (from grader)                                      |
|--------------------------------------------|---------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Phase 1 – Infrastructure Configuration     | CloudFormation, KMS, Secrets Manager, DynamoDB, S3                                    | tc01 (8), tc02 (6), tc03 (8), tc04 (6)                       |
| Phase 2 – Application Development          | API endpoints, DynamoDB persistence, Secrets retrieval                                | tc05 (10), tc06 (8), tc07 (6)                                |
| Phase 3 – Deployment & Integration (CI/CD) | ECR, ECS, CodePipeline, CodeBuild, CodeDeploy                                         | tc08 (6), tc09 (8), tc10 (8), tc11 (8)                       |
| Phase 4 – Observability & Audit            | CloudTrail, CloudWatch                                                                | tc12 (4), tc13 (4)                                           |
| Phase 5 – End-to-End Validation            | Pipeline execution, rollback, security controls                                       | tc14 (4), tc15 (3), tc16 (3)                                 |

**Total:** 100 marks across 16 testcases.

---

## 🏷️ Category Taxonomy

Testcases are tagged with a **category** for grouping and reporting. Common categories (from corpus):

| Category              | Example Checks                                                                 |
|-----------------------|--------------------------------------------------------------------------------|
| `general`             | End-to-end validation, overall compliance                                      |
| `cloudformation`      | Stack creation, resource provisioning, template validation                     |
| `kms`                 | Key creation, encryption configuration, alias setup                            |
| `ecr`                 | Image push, repository creation, lifecycle policies                            |
| `ecs`                 | Fargate service, task definition, ALB integration                              |
| `api`                 | API Gateway endpoints, request validation, Cognito auth                        |
| `dynamodb`            | Table creation, encrypted attributes, query/scan operations                    |
| `s3`                  | Bucket creation, versioning, encryption, pipeline source                       |
| `codedeploy`          | Blue/green deployment, rollback configuration, deployment group                |
| `cloudtrail`          | Trail creation, S3 logging, event validation                                   |
| `cloudwatch`          | Alarms, structured logging, metrics                                            |
| `sqs`                 | Queue creation, DLQ configuration, message handling                            |
| `API_HANDLER`         | Controller logic, exception handling, structured responses                     |
| `DYNAMODB_REPOSITORY` | Repository implementation, KMS-encrypted fields                                |
| `REQUEST_VALIDATION`  | Input validation, error responses                                              |
| `STREAM_PROCESSOR`    | Kinesis/DynamoDB stream processing                                             |
| `SNS_NOTIFICATION`    | Topic creation, subscription, message publishing                               |
| `IDEMPOTENT_WRITES`   | Duplicate detection, conditional writes                                        |
| `FIREHOSE_DELIVERY`   | Data stream delivery, S3 destination                                           |
| `DLQ_HANDLING`        | Dead-letter queue processing, retry logic                                      |

---

## 🔗 Task-Grader-Marks Consistency Contract

### 1. Resource Name Discipline

**Rule:** Resource names stated in the task doc **must match** the names checked by the grader, byte-for-byte.

**Example:**

**Task doc (Activities.md):**
```markdown
Create a KMS key with alias `alias/trade-platform-kms`.
```

**Grader (_Validation):**
```python
expected_alias = "alias/trade-platform-kms"
actual_alias = kms_client.describe_key(KeyId=key_id)['KeyMetadata']['AliasName']
assert actual_alias == expected_alias, f"Expected {expected_alias}, got {actual_alias}"
```

**Common naming patterns (from corpus):**
- **Kebab-case:** `trade-platform-kms`, `trade-api-bucket-dev`, `trade-settlement-api`.
- **Prefixes:** `trade`, `shipment`, `order`, `us`, `cloudformation`, `AWS`, `alias/`.
- **Suffixes:** `-dev`, `-prod`, `-<account-id>`, `-<region>`.

### 2. Marks Declaration in Task Doc

Every task in the task doc **must declare its marks** inline.

**Example:**

```markdown
### Task 1.1: Validate CloudFormation Stack **(Marks = 8)**

Deploy the provided CloudFormation template `cloudformation-template.yaml` with stack name `trade-platform-infra-dev`.
```

**Grader testcase:**
```json
{
  "id": "tc01",
  "name": "testcase1 cloudformation stack",
  "marks": 8,
  "category": "cloudformation",
  "phase": "Phase 1 - Infrastructure Configuration"
}
```

### 3. Phase Completeness

Every phase in the task doc **must have ≥ 1 testcase** in the grader.

**Example (5 phases, 16 testcases):**

| Phase   | Testcase Count | Marks |
|---------|----------------|-------|
| Phase 1 | 4              | 28    |
| Phase 2 | 3              | 24    |
| Phase 3 | 4              | 30    |
| Phase 4 | 2              | 8     |
| Phase 5 | 3              | 10    |

**Total:** 16 testcases, 100 marks.

### 4. No Solution Leakage into _Main

**Forbidden in _Main:**
- Solution code (completed controller methods, repository implementations).
- Answer keys (expected API responses, database records).
- Grader expected values (resource ARNs, encryption keys, secret values).

**Allowed in _Main:**
- Starter code (empty methods, TODO comments).
- Provided infrastructure (Dockerfile, buildspec.yml, appspec.yaml, taskdef.json, CloudFormation template).
- Hints and guidance (architecture diagrams, resource checklists, Postman collections).

---

## 📋 Canonical Testcase Example

From the worked example: **Brokerage Trade Settlement Platform CI/CD and Security Transformation on AWS Assessment**.

```json
{
  "total_marks": 100,
  "testcases": [
    {
      "id": "tc01",
      "name": "testcase1 cloudformation stack",
      "marks": 8,
      "category": "cloudformation",
      "phase": "Phase 1 - Infrastructure Configuration",
      "check_kind": "resource",
      "resourceType": "AWS::CloudFormation::Stack",
      "resourceName": "trade-platform-infra-dev",
      "expectedProperties": {
        "StackStatus": "CREATE_COMPLETE",
        "Outputs": ["VpcId", "SubnetIds", "SecurityGroupId"]
      }
    },
    {
      "id": "tc02",
      "name": "testcase2 kms key",
      "marks": 6,
      "category": "kms",
      "phase": "Phase 1 - Infrastructure Configuration",
      "check_kind": "resource",
      "resourceType": "AWS::KMS::Key",
      "resourceName": "trade-platform-kms",
      "expectedProperties": {
        "KeyState": "Enabled",
        "Alias": "alias/trade-platform-kms"
      }
    },
    {
      "id": "tc05",
      "name": "testcase5 trade api endpoints",
      "marks": 10,
      "category": "api",
      "phase": "Phase 2 - Application Development",
      "check_kind": "api",
      "endpoints": [
        {
          "path": "/trades",
          "method": "POST",
          "expectedStatusCode": 201,
          "expectedFields": ["tradeId", "timestamp"]
        },
        {
          "path": "/trades/{id}",
          "method": "GET",
          "expectedStatusCode": 200,
          "expectedFields": ["tradeId", "status", "encryptedAccountNumber"]
        }
      ]
    },
    {
      "id": "tc14",
      "name": "testcase14 pipeline zero downtime",
      "marks": 4,
      "category": "general",
      "phase": "Phase 5 - End-to-End Validation",
      "check_kind": "e2e",
      "scenario": "Upload new code to S3, trigger pipeline, verify blue/green deployment with zero downtime",
      "steps": [
        "Upload trade-settlement-api.zip to S3 source bucket",
        "Wait for pipeline execution to complete",
        "Verify ECS service has two target groups (blue and green)",
        "Verify traffic shift from blue to green",
        "Verify API remains available throughout deployment"
      ],
      "expectedOutcome": "Pipeline succeeds, API returns 200 OK during entire deployment"
    }
  ]
}
```

---

## ⚠️ Strict Rules

1. **Do NOT** allow `sum(testcase.marks) ≠ total_marks`. The grader will reject the package.
2. **Do NOT** create orphan phases (phases with zero testcases).
3. **Do NOT** create orphan testcases (testcases not mapped to a task in the task doc).
4. **Do NOT** put solution code, answer keys, or grader expected values into _Main.
5. **Do NOT** use approximate or rounded marks. Use exact integers or decimals that sum precisely.
6. **Do NOT** use inconsistent resource names between task doc and grader.

---

## 📌 Output Expectations

When you author a skill package, the AI agent expects:

1. **A testcase manifest** (JSON or Python dict) listing all testcases with `id`, `name`, `marks`, `category`, `phase`.
2. **A marks validation** proving `sum(marks) == total_marks`.
3. **A phase-task-testcase mapping table** showing alignment.
4. **A resource name registry** listing all AWS resource names used in the task doc and grader.

**Example output (in `grader-design.md` or `testcase-manifest.json`):**

```json
{
  "assessment_title": "Brokerage Trade Settlement Platform CI/CD and Security Transformation on AWS Assessment",
  "total_marks": 100,
  "duration_minutes": 75,
  "testcase_count": 16,
  "phase_count": 5,
  "testcases": [
    {"id": "tc01", "name": "testcase1 cloudformation stack", "marks": 8, "category": "cloudformation", "phase": "Phase 1 - Infrastructure Configuration"},
    {"id": "tc02", "name": "testcase2 kms key", "marks": 6, "category": "kms", "phase": "Phase 1 - Infrastructure Configuration"},
    ...
    {"id": "tc16", "name": "testcase16 api security kms secrets", "marks": 3, "category": "kms", "phase": "Phase 5 - End-to-End Validation"}
  ],
  "marks_validation": {
    "sum": 100,
    "expected": 100,
    "valid": true
  },
  "resource_registry": [
    "cloudformation-template.yaml",
    "trade-platform-infra-dev",
    "trade-platform-kms",
    "alias/trade-platform-kms",
    "trade-app-secrets",
    "trade-api-bucket-373954893424-dev",
    "trade-settlement-api",
    "trade-platform-codedeploy-app",
    "trade-platform-bluegreen-dg",
    "trade-platform-cicd-pipeline",
    "trade-platform-trail"
  ]
}
```

---

## 🧠 Quality Check (Before Finalizing)

- [ ] Every testcase has `id`, `name`, `marks`, `category`, `phase`.
- [ ] `sum(testcase.marks) == total_marks` (exact, no rounding).
- [ ] Every phase in the task doc has ≥ 1 testcase in the grader.
- [ ] Every testcase maps to a task in the task doc.
- [ ] Resource names in task doc match grader checks byte-for-byte.
- [ ] No solution code, answer keys, or grader expected values in _Main.
- [ ] Testcase categories align with AWS services and capabilities.
- [ ] Marks distribution reflects task difficulty (harder tasks = more marks).

---

**End of file.**
