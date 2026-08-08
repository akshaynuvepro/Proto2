---
name: "Nuvepro TLS House Style for AWS Assessments"
description: "Common AWS services, testcase categories, typical phase count, total-marks and duration norms, required _Main files, and the exact resource-naming discipline."
---

# Nuvepro TLS House Style for AWS Assessments

## 🎯 Purpose

Define the **Nuvepro TLS house style** for AWS cloud assessments: common services, testcase categories, typical phase count, total-marks and duration norms, required _Main files, and the exact resource-naming discipline.

Every AWS assessment you author **must** follow these conventions to ensure consistency, gradeability, and learner clarity.

---

## 🧠 Core Principles

1. **Real-world, hands-on difficulty**  
   - Debugging, decision-making, integration tasks—not trivial MCQs.
   - Learners configure, code, deploy, and validate AWS resources.

2. **Exact resource-naming discipline**  
   - Resource names stated in the task doc **must** match, byte-for-byte, the names checked by the grader.
   - No extra spaces, no case differences, no typos.

3. **Triplet completeness**  
   - Every assessment is three repos: `<base>_Main`, `<base>_Solution`, `<base>_Validation`.
   - Never place solution code, answer keys, or grader expected-values into `_Main`.

4. **Testcase-to-task mapping**  
   - Every phase has ≥ 1 testcase.
   - Every testcase maps to a task in the task doc.
   - `sum(testcase.marks) == total_marks`.

---

## 📊 Typical Assessment Parameters

| Parameter              | Default | Range / Values                  |
|------------------------|---------|---------------------------------|
| **Duration (minutes)** | 42      | 40, 45, 75                      |
| **Total Marks**        | 100     | 54, 100                         |
| **Phase Count**        | 5       | 5 (median, min, max all = 5)    |
| **Testcase Count**     | 14      | 14 (median), 14 (min), 16 (max) |

**Guidance:**
- **Short assessments:** 40–45 minutes, 54–100 marks, 3–5 phases, 10–14 testcases.
- **Standard assessments:** 75 minutes, 100 marks, 5 phases, 14–16 testcases.
- **Complex assessments:** May extend to 90 minutes, 120 marks, 6 phases, 18+ testcases (rare).

---

## 🔧 Top AWS Services (by frequency)

1. **API Gateway**
2. **DynamoDB**
3. **ECR**
4. **IAM**
5. **ECS Fargate**
6. **Cognito**
7. **S3**
8. **CloudWatch**
9. **Kinesis Data Streams**
10. **SQS**
11. **SNS**
12. **Lambda**
13. **Kinesis Data Firehose**
14. **CloudFormation**
15. **KMS**
16. **Secrets Manager**
17. **Systems Manager Parameter Store**
18. **CodePipeline**
19. **CodeBuild**
20. **CodeDeploy**
21. **CloudTrail**

**Guidance:**
- Prefer **serverless** and **managed services** (Lambda, Fargate, API Gateway, DynamoDB).
- Include **security** (KMS, Secrets Manager, IAM) and **observability** (CloudWatch, CloudTrail).
- Use **CI/CD** (CodePipeline, CodeBuild, CodeDeploy) for deployment scenarios.

---

## 🏷️ Testcase Categories (by frequency)

- `general` (cross-cutting, end-to-end)
- `api` (API Gateway, REST endpoints)
- `dynamodb` (table, queries, encryption)
- `ecr` (container registry)
- `kms` (encryption, key management)
- `ecs` (Fargate, task definitions, services)
- `s3` (buckets, objects, policies)
- `cloudformation` (stack validation)
- `codedeploy` (blue/green, rollback)
- `cloudtrail` (audit logging)
- `cloudwatch` (alarms, logs, metrics)
- `sqs` (queues, DLQ)
- `sns` (topics, subscriptions)
- `lambda` (functions, triggers)
- `cognito` (user pools, authentication)
- `API_HANDLER` (application-level API logic)
- `DYNAMODB_REPOSITORY` (application-level DB logic)
- `REQUEST_VALIDATION` (input validation)
- `STREAM_PROCESSOR` (Kinesis, event processing)
- `SNS_NOTIFICATION` (notification logic)
- `IDEMPOTENT_WRITES` (idempotency checks)
- `FIREHOSE_DELIVERY` (Kinesis Firehose)
- `DLQ_HANDLING` (dead-letter queue logic)

**Guidance:**
- Use **service-level categories** (e.g., `api`, `dynamodb`, `kms`) for infrastructure/resource checks.
- Use **capability-level categories** (e.g., `API_HANDLER`, `REQUEST_VALIDATION`, `STREAM_PROCESSOR`) for application-level code checks.
- Group testcases by category for clarity in the grader.

---

## 📛 Resource Naming Conventions

### **Kebab-case dominance**
- **82.5%** of resource names use kebab-case (e.g., `trade-platform-kms`, `trade-api-bucket-dev`).
- **1.8%** use path-style (e.g., `alias/trade-platform-kms`).
- Remainder: PascalCase (CloudFormation logical IDs), camelCase (rare), or AWS defaults (e.g., `CodeDeployDefault.ECSAllAtOnce`).

### **Common prefixes** (by frequency)
1. `trade` (domain/app name)
2. `shipment` (domain/app name)
3. `order` (domain/app name)
4. `us` (region prefix, e.g., `us-east-1`)
5. `cloudformation` (template files)
6. `AWS` (AWS-provided defaults or checklists)
7. `alias/` (KMS alias prefix)
8. `30` (numeric prefixes, e.g., retention days)

### **Canonical examples**
```
cloudformation-template.yaml
trade-platform-infra-dev
AWS-Resources-Checklist.md
trade-platform-kms
trade-app-secrets
us-east-1
alias/trade-platform-kms
trade-api-bucket-373954893424-dev
trade-settlement-api
trade-platform-codedeploy-app
trade-platform-bluegreen-dg
CodeDeployDefault.ECSAllAtOnce
trade-platform-cicd-pipeline
trade-platform-trail
trade-api-high-latency
trade-api-5xx-errors
trade-api-unhealthy-hosts
trade-api-green-unhealthy
trade-platform-cluster
trade-api-service
```

### **Naming rules**
1. **Prefix with domain/app name** (e.g., `trade-`, `shipment-`, `order-`).
2. **Suffix with environment** (e.g., `-dev`, `-prod`) if multi-environment.
3. **Suffix with AWS account ID** if globally unique (e.g., S3 bucket: `trade-api-bucket-373954893424-dev`).
4. **Use kebab-case** unless AWS service requires otherwise (e.g., CloudFormation logical IDs use PascalCase).
5. **KMS aliases** use `alias/` prefix (e.g., `alias/trade-platform-kms`).
6. **CloudWatch alarms** use descriptive names (e.g., `trade-api-high-latency`, `trade-api-5xx-errors`).
7. **CodeDeploy deployment groups** use descriptive names (e.g., `trade-platform-bluegreen-dg`).
8. **CloudTrail trails** use descriptive names (e.g., `trade-platform-trail`).

---

## 📁 Required _Main Files

Every `<base>_Main` repo **must** include:

1. **Task doc** (one of):
   - `Assessment-Activities.md` (preferred)
   - `Assessment_Activities.md` (alternate)

2. **Starter code project** (e.g., `trade-settlement-api/`):
   - Application source code (Java, Python, Node.js, etc.)
   - `Dockerfile`, `buildspec.yml`, `appspec.yaml`, `taskdef.json` (if applicable)
   - `pom.xml`, `package.json`, `requirements.txt` (dependency manifests)
   - `README.md` (project-level instructions)
   - **Empty or incomplete methods/functions** (learners complete them)
   - **No solution code, answer keys, or expected values**

3. **CloudFormation template** (if infrastructure-as-code):
   - `cloudformation-template.yaml` (or `.json`)
   - Provisions base infrastructure (VPC, subnets, IAM roles, etc.)

4. **AWS Resources Checklist** (optional but recommended):
   - `AWS-Resources-Checklist.md`
   - Lists all AWS resources learners must create (with exact names)

5. **Helper scripts** (optional):
   - `ECS-Service-Creation/Create-ECS-Service-With-CLI.py`
   - `ECS-Service-Creation/Create-ECS-Service-With-SDK.py`
   - Provide CLI/SDK examples (not full solutions)

6. **Images** (optional):
   - `images/error.png` (screenshots, diagrams)

7. **Config YAML** (optional):
   - `config.yaml` (assessment metadata, environment variables)

8. **Postman collection** (if API testing):
   - `trade-settlement-api.postman_collection.json`

---

## 🧪 Testcase Schema

Every testcase **must** include:

| Field        | Description                                                                 |
|--------------|-----------------------------------------------------------------------------|
| `id`         | Stable ID (e.g., `TC001`, `tc01`)                                           |
| `name`       | Human-readable check title (e.g., `testcase1 cloudformation stack`)         |
| `marks`      | Positive number; all marks sum to `total_marks`                             |
| `category`   | Grouping tag (service or capability, e.g., `api`, `kms`, `API_HANDLER`)     |
| `phase`      | The phase/milestone this check belongs to (e.g., `Phase 1 - Infrastructure`)|
| `check_kind` | `api`, `resource`, `db`, `code`, `e2e` (format-specific)                    |
| `details`    | Format-specific fields (e.g., `endpoint`, `expectedStatusCode`, `resourceName`, `expectedValues`) |

**Grouping:**
- Testcases are grouped into **phases/milestones** matching the task doc.
- Each phase has ≥ 1 testcase.

**Marks rule:**
- `sum(testcase.marks) == total_marks`

---

## 🏗️ Typical Phase Structure

**5 phases** (standard):

1. **Phase 1: Infrastructure Configuration**
   - CloudFormation stack validation
   - KMS key creation
   - Secrets Manager / Parameter Store setup
   - DynamoDB table, S3 bucket creation

2. **Phase 2: Application Development**
   - API endpoint implementation
   - DynamoDB persistence with KMS encryption
   - Secrets/Parameter retrieval (no hardcoded credentials)

3. **Phase 3: Deployment & Integration (CI/CD)**
   - ECR image creation
   - ECS Fargate deployment (with ALB, API Gateway, Cognito)
   - CodePipeline, CodeBuild integration
   - CodeDeploy blue/green deployment

4. **Phase 4: Observability & Audit**
   - CloudTrail audit logging
   - CloudWatch alarms, structured logging

5. **Phase 5: End-to-End Validation**
   - Pipeline execution, zero-downtime deployment
   - Induced failure, automated rollback
   - API security, KMS encryption, audit controls

**Guidance:**
- Phases build on each other (infrastructure → app → deployment → observability → validation).
- Each phase has 2–5 tasks.
- Each task maps to 1–3 testcases.

---

## 🎓 Grader Format

**Recommended:** `python_harness` (3 of 4 assessments use this).

**Alternate:** `json_testcases` (1 of 4 assessments).

**Python harness structure:**
```
<base>_Validation/
  grader.py              # Main grader entry point
  testcases/
    tc01_cloudformation.py
    tc02_kms.py
    tc03_secrets.py
    ...
  utils/
    aws_client.py        # Boto3 helpers
    assertions.py        # Custom assertions
  requirements.txt       # Boto3, pytest, etc.
  README.md              # Grader setup instructions
```

**JSON testcases structure:**
```
<base>_Validation/
  testcases.json         # All testcases in JSON
  grader.py              # Reads JSON, executes checks
  requirements.txt
  README.md
```

---

## ⚠️ Strict Rules

**Do NOT:**
1. Place solution code, answer keys, or grader expected-values into `_Main`.
2. Use different resource names in the task doc vs. grader (byte-for-byte match required).
3. Create testcases that don't map to a task in the task doc.
4. Assign marks that don't sum to `total_marks`.
5. Create phases with zero testcases.
6. Use trivial MCQ-style checks (e.g., "Did you read the doc?").
7. Hardcode credentials, secrets, or sensitive data in `_Main` code.
8. Use PascalCase or camelCase for AWS resource names (unless AWS service requires it).
9. Omit the task doc (`Assessment-Activities.md`).
10. Omit the `_Solution` or `_Validation` repo.

---

## 📌 Output Expectations

When authoring an AWS assessment, you **must** produce:

1. **Task doc** (`Assessment-Activities.md`):
   - YAML front-matter (name, description)
   - Title, scenario, duration, total marks
   - 5 phases with 2–5 tasks each
   - Exact resource names (matching grader)
   - Marks per task (summing to total)

2. **Starter code project** (in `_Main`):
   - Incomplete methods/functions
   - Dockerfile, buildspec, appspec, taskdef (if applicable)
   - No solution code

3. **CloudFormation template** (if applicable):
   - Provisions base infrastructure
   - Learners extend/complete it

4. **AWS Resources Checklist** (optional):
   - Lists all resources with exact names

5. **Testcases** (in `_Validation`):
   - 14–16 testcases (median 14)
   - Grouped by phase
   - Categories: `api`, `dynamodb`, `kms`, `ecs`, `cloudformation`, etc.
   - Marks sum to total

6. **Solution reference** (in `_Solution`):
   - Complete, working code
   - All resources created
   - Passes all testcases

---

## 🧠 Quality Check

Before finalizing, verify:

- [ ] Task doc states **exact resource names** (byte-for-byte match with grader).
- [ ] `sum(testcase.marks) == total_marks`.
- [ ] Every phase has ≥ 1 testcase.
- [ ] Every testcase maps to a task in the task doc.
- [ ] No solution code, answer keys, or expected-values in `_Main`.
- [ ] Starter code is **incomplete** (learners must complete it).
- [ ] Resource names use **kebab-case** (unless AWS service requires otherwise).
- [ ] Grader checks **real AWS resources** (not mocked).
- [ ] Phases build on each other (infrastructure → app → deployment → observability → validation).
- [ ] Duration, total marks, phase count, testcase count are within norms.
- [ ] Top AWS services (API Gateway, DynamoDB, ECR, IAM, ECS, etc.) are used appropriately.
- [ ] Testcase categories match house style (e.g., `api`, `kms`, `API_HANDLER`).
- [ ] CloudFormation template (if used) provisions base infrastructure only.
- [ ] AWS Resources Checklist (if used) lists all resources with exact names.
- [ ] Postman collection (if used) includes all API endpoints.
- [ ] Helper scripts (if used) provide examples, not full solutions.

---

**End of house-style.md**
