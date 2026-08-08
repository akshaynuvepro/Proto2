---
name: "Main Repo Structure & Task Doc"
description: "How to build the _Main repository: file tree, Assessment-Activities.md skeleton with all required sections, phases with exact resource names, and the learner-safe rule."
---

# Main Repo (_Main) – Learner-Facing Repository

## 🎯 Purpose

The **_Main** repository is the **learner-facing workspace**. It contains:
- The task document (`Assessment-Activities.md`)
- Starter code, configuration files, and scaffolding
- Supporting assets (images, templates, scripts)
- **Zero solution code, answer keys, or grader expected values**

The learner clones this repo, reads the task doc, and completes the assessment by building/configuring AWS resources with the exact names specified.

---

## 🧠 Core Principles

1. **Learner-safe**: Never include solution code, answer keys, or grader expected values.
2. **Exact resource names**: The task doc states precise resource names (kebab-case preferred); the grader checks them byte-for-byte.
3. **Starter scaffolding**: Provide partial code, empty methods, or templates so learners focus on AWS integration, not boilerplate.
4. **Real-world scenario**: Frame the assessment as a business problem (legacy migration, compliance gap, incident response).
5. **Phase-driven structure**: Organize tasks into 5 phases (median = 5, range 5–5 in house style); each phase maps to >= 1 testcase.

---

## 🔥 Difficulty Standard

- **Hands-on AWS configuration**: Learners create KMS keys, Secrets Manager secrets, DynamoDB tables, ECS services, CodePipeline pipelines, CloudTrail trails, etc.
- **Code completion**: Fill in empty controller methods, repository logic, or integration points (KMS encrypt/decrypt, Secrets Manager retrieval).
- **Debugging & decision-making**: Learners must read CloudFormation templates, understand `buildspec.yml` / `appspec.yaml`, and wire services together.
- **No trivial MCQ**: Every task requires creating/configuring a real AWS resource or writing integration code.

---

## ⚠️ Strict Rules

**Do NOT:**
- Place solution code (completed methods, correct SQL queries, full Lambda handlers) in _Main.
- Include answer keys, grader expected values, or testcase pass/fail logic in _Main.
- Use vague resource names like "my-bucket" or "test-key"; always specify exact names (e.g., `trade-platform-kms`, `alias/trade-platform-kms`).
- Omit marks from task bullets; every task must show `**(Marks = X)**`.
- Let `sum(testcase.marks) ≠ total_marks`.
- Create phases with zero testcases.

**Do:**
- Provide partial code with `// TODO: Implement` comments.
- Include CloudFormation templates, Dockerfiles, `buildspec.yml`, `appspec.yaml`, `taskdef.json` if they are **given** scaffolding.
- State exact resource names in the task doc (e.g., "Create a KMS key with alias `alias/trade-platform-kms`").
- Use kebab-case for ~82% of resource names (house style).
- Provide a checklist file (e.g., `AWS-Resources-Checklist.md`) listing all required resources.

---

## 📂 File Tree Structure

```
<base>_Main/
├── Assessment-Activities.md          # Task document (see skeleton below)
├── AWS-Resources-Checklist.md        # Optional: list of all resources to create
├── cloudformation-template.yaml      # Optional: provided CFN template
├── images/
│   └── error.png                     # Optional: screenshots, diagrams
├── <project-folder>/                 # Starter code project
│   ├── Dockerfile                    # Provided
│   ├── buildspec.yml                 # Provided
│   ├── appspec.yaml                  # Provided
│   ├── taskdef.json                  # Provided
│   ├── pom.xml / package.json / requirements.txt
│   ├── src/
│   │   └── main/
│   │       └── java/com/trade/app/
│   │           ├── controller/
│   │           │   └── TradeController.java   # Empty methods with TODOs
│   │           ├── repository/
│   │           │   └── DynamoDbTradeRepositoryImpl.java
│   │           ├── security/
│   │           │   ├── KMSServiceImpl.java
│   │           │   ├── SecretManagerServiceImpl.java
│   │           │   └── SSMServiceImpl.java
│   │           └── ...
│   └── ...
└── ECS-Service-Creation/             # Optional: helper scripts
    ├── Create-ECS-Service-With-CLI.py
    └── Create-ECS-Service-With-SDK.py
```

**Common file names seen:**
- `Assessment-Activities.md` or `Assessment_Activities.md` (prefer hyphen)
- `AWS-Resources-Checklist.md`
- `cloudformation-template.yaml`
- `images/error.png`
- Starter project folder (e.g., `trade-settlement-api/`, `order-processing-service/`)

---

## 📝 Assessment-Activities.md Skeleton

**YAML front-matter** (required):

```yaml
---
name: "<Assessment Title>"
description: "<One-sentence summary of the assessment>"
---
```

**Title line** (after front-matter):

```markdown
# <Assessment Title>
```

**Sections** (in order):

### 1. Scenario

```markdown
## Scenario

<2–4 paragraphs describing the business context, legacy pain points, and the transformation goal.>

Example:
"A brokerage firm is replacing its legacy trade settlement system with a modern, cloud-native settlement platform that records executed trades and tracks their settlement status. The platform must protect sensitive trade and account information, govern software releases, and deliver releases with zero downtime.

In the last quarter, an unaudited manual deployment took the settlement service offline for two hours during market close processing, a configuration change exposed a credential in plaintext, and a compliance review flagged the absence of an audit trail for privileged actions. The firm now requires encryption of sensitive data, secret and configuration management, an automated and auditable CI/CD pipeline, and zero-downtime blue/green deployments with automated rollback.

The outgoing engineering team left behind a partially implemented Java Spring Boot Trade Settlement API with empty controller methods. AWS KMS encryption and AWS Secrets Manager retrieval calls are already wired in the code, but no key, secret, parameter, S3 bucket, or CloudTrail trail has been created — you must create them. A completed Dockerfile, a `buildspec.yml`, an `appspec.yaml`, a `taskdef.json`, and an AWS CloudFormation template are provided.

Your responsibility is to complete the application and stand up the governed, secure delivery pipeline below."
```

### 2. Assessment Details

```markdown
## Assessment Details

- **Duration:** <X> minutes  
  *(Default = 42 min; common values: 40, 45, 75)*
- **Total Marks:** <Y>  
  *(Default = 100; seen: 54, 100)*
- **Difficulty:** <Level>  
  *(e.g., Intermediate, Advanced)*
```

### 3. AWS Services Used

```markdown
## AWS Services Used

<Bullet list of all AWS services the learner will interact with, in descending order of prominence.>

Example:
- Amazon ECR
- Amazon ECS Fargate
- Amazon API Gateway
- Amazon DynamoDB
- Amazon Cognito
- AWS KMS
- AWS Secrets Manager
- AWS Systems Manager Parameter Store
- Amazon S3
- AWS CloudFormation
- AWS CodePipeline
- AWS CodeBuild
- AWS CodeDeploy
- Amazon CloudWatch
- AWS CloudTrail
- AWS IAM
```

### 4. Prerequisites

```markdown
## Prerequisites

- AWS Account with all required permissions (Administrator or equivalent)
- AWS CLI installed and configured
- Docker installed (if building container images locally)
- <Language> SDK installed (e.g., Java 17, Node.js 18, Python 3.11)
- Postman or `curl` for API testing
- Basic familiarity with <services> (e.g., ECS, CodePipeline, KMS)
```

### 5. Assessment Phases

```markdown
## Assessment Phases

<5 phases (median = 5, range 5–5). Each phase has:
  - Phase number and name
  - Objective (optional, can be empty)
  - Bulleted task list with exact resource names and marks>

Example:

### Phase 1: Infrastructure Configuration

**Objective:** Provision foundational AWS resources using CloudFormation, KMS, Secrets Manager, DynamoDB, and S3.

- **Task 1.1:** Validate CloudFormation infrastructure provisioning. **(Marks = 8)**
  - Deploy the provided `cloudformation-template.yaml` stack with stack name `trade-platform-infra-dev`.
  - Ensure all resources (VPC, subnets, security groups, IAM roles) are created successfully.

- **Task 1.2:** Validate AWS KMS key creation and encryption configuration. **(Marks = 6)**
  - Create a KMS key with alias `alias/trade-platform-kms` in region `us-east-1`.
  - Enable automatic key rotation.

- **Task 1.3:** Validate Secrets Manager and Parameter Store creation and integration. **(Marks = 8)**
  - Create a Secrets Manager secret named `trade-app-secrets` containing a JSON object with keys `dbPassword` and `apiKey`.
  - Create a Systems Manager Parameter Store parameter `/trade/app/environment` with value `production`.

- **Task 1.4:** Validate DynamoDB table and S3 source bucket creation. **(Marks = 6)**
  - Create a DynamoDB table named `trade-settlement-api` with partition key `tradeId` (String).
  - Create an S3 bucket named `trade-api-bucket-<account-id>-dev` (replace `<account-id>` with your AWS account ID).

---

### Phase 2: Application Development

**Objective:** Complete the Trade Settlement API by implementing REST endpoints, DynamoDB persistence, and secret retrieval.

- **Task 2.1:** Validate Trade Settlement API endpoints, request validation, exception handling, and structured logging. **(Marks = 10)**
  - Implement `POST /trades`, `GET /trades/{tradeId}`, `PUT /trades/{tradeId}/status` in `TradeController.java`.
  - Add request validation (e.g., non-null `tradeId`, valid `status` enum).
  - Implement `GlobalExceptionHandler` to return structured JSON error responses.
  - Configure structured JSON logging in `logback-spring.xml`.

- **Task 2.2:** Validate DynamoDB persistence with KMS-encrypted sensitive fields. **(Marks = 8)**
  - Implement `DynamoDbTradeRepositoryImpl` to save/retrieve trades from DynamoDB.
  - Encrypt the `accountNumber` field using KMS before saving; decrypt on retrieval.

- **Task 2.3:** Validate Secrets Manager and Parameter Store retrieval with no hardcoded credentials. **(Marks = 6)**
  - Implement `SecretManagerServiceImpl` to retrieve `trade-app-secrets`.
  - Implement `SSMServiceImpl` to retrieve `/trade/app/environment`.
  - Ensure no hardcoded credentials in code or `application.properties`.

---

### Phase 3: Deployment & Integration (CI/CD)

**Objective:** Build and deploy the containerized API with a fully automated CI/CD pipeline and zero-downtime blue/green deployment.

- **Task 3.1:** Validate container image creation and Amazon ECR deployment. **(Marks = 6)**
  - Build the Docker image using the provided `Dockerfile`.
  - Push the image to an ECR repository named `trade-settlement-api`.

- **Task 3.2:** Validate Amazon ECS Fargate deployment with `CODE_DEPLOY` deployment controller behind the Application Load Balancer and exposed through API Gateway with Cognito authentication. **(Marks = 8)**
  - Create an ECS cluster named `trade-platform-cluster`.
  - Create an ECS service named `trade-api-service` with deployment controller `CODE_DEPLOY`.
  - Register the service with an Application Load Balancer.
  - Create an API Gateway REST API with Cognito User Pool authorizer.

- **Task 3.3:** Validate S3-triggered AWS CodePipeline and AWS CodeBuild integration. **(Marks = 8)**
  - Create a CodePipeline named `trade-platform-cicd-pipeline` triggered by S3 uploads to `trade-api-bucket-<account-id>-dev`.
  - Configure a CodeBuild project using the provided `buildspec.yml`.

- **Task 3.4:** Validate AWS CodeDeploy blue/green deployment and automated rollback configuration. **(Marks = 8)**
  - Create a CodeDeploy application named `trade-platform-codedeploy-app`.
  - Create a deployment group named `trade-platform-bluegreen-dg` with deployment config `CodeDeployDefault.ECSAllAtOnce`.
  - Configure automated rollback on deployment failure or CloudWatch alarm.

---

### Phase 4: Observability & Audit

**Objective:** Enable audit logging and monitoring with CloudTrail and CloudWatch.

- **Task 4.1:** Validate AWS CloudTrail audit logging configuration. **(Marks = 4)**
  - Create a CloudTrail trail named `trade-platform-trail` logging all management events to an S3 bucket.

- **Task 4.2:** Validate structured logging and Amazon CloudWatch alarms configuration. **(Marks = 4)**
  - Create CloudWatch alarms:
    - `trade-api-high-latency` (TargetResponseTime > 2s)
    - `trade-api-5xx-errors` (HTTPCode_Target_5XX_Count > 5)
    - `trade-api-unhealthy-hosts` (UnHealthyHostCount > 0)
    - `trade-api-green-unhealthy` (for blue/green rollback)

---

### Phase 5: End-to-End Validation

**Objective:** Validate the complete pipeline, zero-downtime deployment, rollback, and security controls.

- **Task 5.1:** Validate end-to-end pipeline execution and zero-downtime deployment. **(Marks = 4)**
  - Upload `trade-settlement-api.zip` to the S3 source bucket.
  - Verify CodePipeline triggers, CodeBuild succeeds, and CodeDeploy completes a blue/green deployment with zero downtime.

- **Task 5.2:** Validate induced deployment failure and automated rollback. **(Marks = 3)**
  - Introduce a breaking change (e.g., invalid health check endpoint).
  - Upload the broken code to S3 and verify automated rollback.

- **Task 5.3:** Validate API security, KMS encryption, secret retrieval, and CloudTrail audit controls. **(Marks = 3)**
  - Call the API with a valid Cognito token and verify encrypted `accountNumber` in DynamoDB.
  - Verify CloudTrail logs capture KMS and Secrets Manager API calls.
```

**Phase structure rules:**
- **5 phases** (median = 5, range 5–5).
- Each phase has **>= 1 task**.
- Each task states **exact resource names** (e.g., `trade-platform-kms`, `alias/trade-platform-kms`, `trade-api-bucket-<account-id>-dev`).
- Each task shows **marks** in bold: `**(Marks = X)**`.
- `sum(all task marks) == total_marks`.

---

### 6. Submission Guidelines

```markdown
## Submission Guidelines

1. **Complete all phases** in the order specified.
2. **Use exact resource names** as stated in the task doc (case-sensitive, no extra spaces).
3. **Do not delete or rename** provided files (`Dockerfile`, `buildspec.yml`, `appspec.yaml`, `taskdef.json`, `cloudformation-template.yaml`).
4. **Test your API** using the provided Postman collection or `curl` before final submission.
5. **Verify CloudFormation stack status** is `CREATE_COMPLETE` or `UPDATE_COMPLETE`.
6. **Verify CodePipeline execution** completes successfully at least once.
7. **Check CloudWatch Logs** for structured JSON log entries.
8. **Check CloudTrail** for audit events (KMS, Secrets Manager, CodeDeploy).
9. **Submit your work** by ensuring all AWS resources are created and the grader can validate them.

**Note:** The grader will check resource names, configurations, and API responses byte-for-byte. Any deviation from the specified names or configurations will result in lost marks.
```

---

### 7. Evaluation Criteria

```markdown
## Evaluation Criteria

| Phase | Focus Area | Marks |
|-------|-----------|-------|
| Phase 1 | Infrastructure Configuration | 28 |
| Phase 2 | Application Development | 24 |
| Phase 3 | Deployment & Integration (CI/CD) | 30 |
| Phase 4 | Observability & Audit | 8 |
| Phase 5 | End-to-End Validation | 10 |
| **Total** | | **100** |

**Grading is automated.** The grader will:
- Check CloudFormation stack outputs.
- Verify KMS key alias, Secrets Manager secret, Parameter Store parameter.
- Query DynamoDB for encrypted fields.
- Call API endpoints and validate responses.
- Inspect ECR images, ECS services, CodePipeline executions, CodeDeploy deployments.
- Check CloudTrail logs and CloudWatch alarms.
- Trigger a deployment and verify zero-downtime and rollback behavior.
```

---

### 8. Resources Provided

```markdown
## Resources Provided

- `cloudformation-template.yaml` – CloudFormation template for VPC, subnets, security groups, IAM roles.
- `AWS-Resources-Checklist.md` – Checklist of all AWS resources to create.
- `trade-settlement-api/` – Starter Java Spring Boot project with:
