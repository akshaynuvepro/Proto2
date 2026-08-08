---
name: "Solution Repo Reference"
description: "How to build the _Solution repository: a complete, working implementation that passes every testcase without exposing answers to learners."
---

# Solution Repo (_Solution) – Evaluator-Only Reference Implementation

## 🎯 Purpose

The **_Solution** repo is the **evaluator-only reference answer**. It mirrors the _Main starter project with **all TODOs completed**, so it passes **every testcase** in _Validation. Learners **never** see this repo.

---

## 🧠 Core Principles

- **Mirror _Main structure exactly** (same folder tree, file names, config).
- **Complete every TODO** left in _Main starter code.
- **Pass all testcases** when graded by _Validation.
- **Never expose** this repo to learners (evaluator-only).
- **Document non-obvious decisions** in inline comments (for future authors/reviewers).

---

## 🔥 Difficulty Standard

- **Real-world completeness**: production-ready code (error handling, logging, security best practices).
- **No shortcuts**: if the task doc requires KMS encryption, the solution must encrypt; if it requires structured logging, the solution must log structured JSON.
- **Testable**: every resource name, API response, configuration value must match what _Validation checks byte-for-byte.

---

## ⚠️ Strict Rules

**Do NOT:**

1. **Deviate from exact resource names** stated in the task doc (grader checks byte-for-byte).
2. **Leave TODOs or placeholders** — solution must be 100% complete.
3. **Hardcode secrets or credentials** — use Secrets Manager / Parameter Store / environment variables as the task doc requires.
4. **Skip error handling or logging** if the task doc or testcases validate them.
5. **Commit `.env` files or AWS credentials** to the repo.
6. **Use different AWS regions** than specified in the task doc.
7. **Omit comments** explaining non-obvious implementation choices (e.g., why a specific IAM policy statement, why a particular DynamoDB attribute type).

---

## 📂 Repo Structure

```
<base>_Solution/
├── Assessment-Activities.md          # (copy from _Main, unchanged)
├── AWS-Resources-Checklist.md        # (copy from _Main, unchanged)
├── cloudformation-template.yaml      # (copy from _Main, unchanged if provided complete)
├── images/
│   └── error.png                     # (copy from _Main)
├── trade-settlement-api/             # (starter code from _Main, now COMPLETED)
│   ├── src/
│   │   └── main/
│   │       └── java/
│   │           └── com/trade/app/
│   │               ├── controller/
│   │               │   └── TradeController.java       # ✅ All endpoints implemented
│   │               ├── repository/
│   │               │   └── DynamoDbTradeRepositoryImpl.java  # ✅ KMS encrypt/decrypt wired
│   │               ├── security/
│   │               │   ├── KMSServiceImpl.java        # ✅ encrypt/decrypt methods complete
│   │               │   ├── SecretManagerServiceImpl.java  # ✅ retrieval logic complete
│   │               │   └── SSMServiceImpl.java        # ✅ parameter retrieval complete
│   │               └── service/
│   │                   └── TradeServiceImpl.java      # ✅ business logic complete
│   ├── Dockerfile                    # (copy from _Main, unchanged if provided)
│   ├── buildspec.yml                 # (copy from _Main, unchanged if provided)
│   ├── appspec.yaml                  # (copy from _Main, unchanged if provided)
│   ├── taskdef.json                  # (copy from _Main, unchanged if provided)
│   └── pom.xml                       # (copy from _Main, unchanged if provided)
└── ECS-Service-Creation/
    ├── Create-ECS-Service-With-CLI.py   # (copy from _Main, unchanged)
    └── Create-ECS-Service-With-SDK.py   # (copy from _Main, unchanged)
```

**Key difference from _Main**: every `// TODO` is replaced with working code.

---

## 📌 Output Expectations

### 1. **Completed Application Code**

**Example (Java Spring Boot Trade Settlement API):**

**_Main starter** (`TradeController.java`):
```java
@PostMapping
public ResponseEntity<TradeResponse> createTrade(@Valid @RequestBody TradeRequest request) {
    // TODO: Implement trade creation logic
    // TODO: Call tradeService.createTrade(request)
    // TODO: Return 201 Created with TradeResponse
    return null;
}
```

**_Solution** (`TradeController.java`):
```java
@PostMapping
public ResponseEntity<TradeResponse> createTrade(@Valid @RequestBody TradeRequest request) {
    logger.info("Creating trade: symbol={}, quantity={}", request.getSymbol(), request.getQuantity());
    TradeResponse response = tradeService.createTrade(request);
    logger.info("Trade created: tradeId={}", response.getTradeId());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
```

**_Solution** (`DynamoDbTradeRepositoryImpl.java`):
```java
@Override
public Trade save(Trade trade) {
    // Encrypt sensitive fields before saving
    String encryptedAccountNumber = kmsService.encrypt(trade.getAccountNumber());
    String encryptedCounterparty = kmsService.encrypt(trade.getCounterparty());
    
    Map<String, AttributeValue> item = new HashMap<>();
    item.put("tradeId", AttributeValue.builder().s(trade.getTradeId()).build());
    item.put("symbol", AttributeValue.builder().s(trade.getSymbol()).build());
    item.put("quantity", AttributeValue.builder().n(String.valueOf(trade.getQuantity())).build());
    item.put("price", AttributeValue.builder().n(String.valueOf(trade.getPrice())).build());
    item.put("accountNumber", AttributeValue.builder().s(encryptedAccountNumber).build());
    item.put("counterparty", AttributeValue.builder().s(encryptedCounterparty).build());
    item.put("status", AttributeValue.builder().s(trade.getStatus()).build());
    item.put("timestamp", AttributeValue.builder().s(trade.getTimestamp()).build());
    
    PutItemRequest putRequest = PutItemRequest.builder()
        .tableName(Constants.DYNAMODB_TABLE_NAME)
        .item(item)
        .build();
    
    dynamoDbClient.putItem(putRequest);
    logger.info("Trade saved to DynamoDB: tradeId={}", trade.getTradeId());
    return trade;
}
```

---

### 2. **Infrastructure Resources Created**

If the task doc requires **manual resource creation** (KMS key, Secrets Manager secret, S3 bucket, CloudTrail trail), document the **exact AWS CLI commands** or **CloudFormation snippet** used in a `SOLUTION-NOTES.md` (evaluator-only, not in _Main).

**Example (`SOLUTION-NOTES.md`):**
```markdown
# Solution Implementation Notes

## Phase 1: Infrastructure Configuration

### KMS Key
```bash
aws kms create-key \
  --description "Trade Platform KMS Key" \
  --region us-east-1 \
  --output json > kms-key.json

KEY_ID=$(jq -r '.KeyMetadata.KeyId' kms-key.json)

aws kms create-alias \
  --alias-name alias/trade-platform-kms \
  --target-key-id $KEY_ID \
  --region us-east-1
```

### Secrets Manager Secret
```bash
aws secretsmanager create-secret \
  --name trade-app-secrets \
  --secret-string '{"db_password":"P@ssw0rd123","api_key":"sk-1234567890abcdef"}' \
  --region us-east-1
```

### S3 Source Bucket
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb s3://trade-api-bucket-${ACCOUNT_ID}-dev --region us-east-1
```

### CloudTrail Trail
```bash
aws cloudtrail create-trail \
  --name trade-platform-trail \
  --s3-bucket-name trade-api-bucket-${ACCOUNT_ID}-dev \
  --is-multi-region-trail \
  --region us-east-1

aws cloudtrail start-logging \
  --name trade-platform-trail \
  --region us-east-1
```
```

---

### 3. **CloudFormation Stack (if applicable)**

If the task doc provides a **partial CloudFormation template**, complete it in _Solution.

**Example (completing missing resources):**

**_Main** (`cloudformation-template.yaml`):
```yaml
Resources:
  # TODO: Add ECS Cluster
  # TODO: Add Application Load Balancer
  # TODO: Add Target Groups (blue/green)
```

**_Solution** (`cloudformation-template.yaml`):
```yaml
Resources:
  TradePlatformCluster:
    Type: AWS::ECS::Cluster
    Properties:
      ClusterName: trade-platform-cluster
      CapacityProviders:
        - FARGATE
        - FARGATE_SPOT
      DefaultCapacityProviderStrategy:
        - CapacityProvider: FARGATE
          Weight: 1

  TradeALB:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Name: trade-api-alb
      Subnets:
        - !Ref PublicSubnet1
        - !Ref PublicSubnet2
      SecurityGroups:
        - !Ref ALBSecurityGroup
      Scheme: internet-facing
      Type: application

  TradeTargetGroupBlue:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      Name: trade-api-tg-blue
      Port: 8080
      Protocol: HTTP
      VpcId: !Ref VPC
      TargetType: ip
      HealthCheckPath: /actuator/health
      HealthCheckIntervalSeconds: 30
      HealthCheckTimeoutSeconds: 5
      HealthyThresholdCount: 2
      UnhealthyThresholdCount: 3

  TradeTargetGroupGreen:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      Name: trade-api-tg-green
      Port: 8080
      Protocol: HTTP
      VpcId: !Ref VPC
      TargetType: ip
      HealthCheckPath: /actuator/health
      HealthCheckIntervalSeconds: 30
      HealthCheckTimeoutSeconds: 5
      HealthyThresholdCount: 2
      UnhealthyThresholdCount: 3
```

---

### 4. **Deployment Artifacts**

- **Docker image** built and pushed to ECR.
- **ECS service** created with `CODE_DEPLOY` deployment controller.
- **CodePipeline** triggered by S3 upload.
- **CodeDeploy blue/green deployment** configured with automated rollback.

**Document the deployment steps** in `SOLUTION-NOTES.md`:

```markdown
## Phase 3: Deployment & Integration

### ECR Image Push
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

docker build -t trade-settlement-api ./trade-settlement-api
docker tag trade-settlement-api:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/trade-settlement-api:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/trade-settlement-api:latest
```

### ECS Service Creation
```bash
aws ecs create-service \
  --cluster trade-platform-cluster \
  --service-name trade-api-service \
  --task-definition trade-settlement-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --deployment-controller type=CODE_DEPLOY \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-zzz],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:${ACCOUNT_ID}:targetgroup/trade-api-tg-blue/xxx,containerName=trade-api,containerPort=8080" \
  --region us-east-1
```

### CodePipeline Trigger
```bash
cd trade-settlement-api
zip -r trade-settlement-api.zip .
aws s3 cp trade-settlement-api.zip s3://trade-api-bucket-${ACCOUNT_ID}-dev/
```
```

---

### 5. **Testcase Alignment**

Every testcase in _Validation must **pass** when run against _Solution.

**Example mapping (from worked example):**

| Testcase ID | Check | Solution Evidence |
|-------------|-------|-------------------|
| `tc01` | CloudFormation stack `trade-platform-infra-dev` exists | Stack created with `aws cloudformation create-stack` |
| `tc02` | KMS key alias `alias/trade-platform-kms` exists | Key created with `aws kms create-key` + `create-alias` |
| `tc05` | `POST /trades` returns 201 with `tradeId` | `TradeController.createTrade()` implemented |
| `tc06` | DynamoDB `accountNumber` field is KMS-encrypted | `DynamoDbTradeRepositoryImpl.save()` calls `kmsService.encrypt()` |
| `tc14` | Pipeline deploys without downtime | CodeDeploy blue/green deployment configured |

---

## 🧠 Quality Check (Before Finalizing)

- [ ] **All TODOs removed** from starter code.
- [ ] **All resource names match** task doc exactly (byte-for-byte).
- [ ] **All testcases pass** when _Validation runs against _Solution.
- [ ] **No hardcoded secrets** (use Secrets Manager / Parameter Store / env vars).
- [ ] **No AWS credentials committed** to repo.
- [ ] **Inline comments explain** non-obvious implementation choices.
- [ ] **`SOLUTION-NOTES.md` documents** manual resource creation steps (if applicable).
- [ ] **CloudFormation template complete** (if task doc provides partial template).
- [ ] **Deployment artifacts created** (Docker image in ECR, ECS service running, pipeline triggered).
- [ ] **Error handling and logging** implemented as task doc requires.
- [ ] **Security best practices** followed (least-privilege IAM, encryption at rest/in transit, no public S3 buckets unless required).

---

## 📌 Final Deliverable

A **complete, working implementation** that:
1. **Passes every testcase** in _Validation.
2. **Mirrors _Main structure** (same files, folders, config).
3. **Documents manual steps** in `SOLUTION-NOTES.md` (evaluator-only).
4. **Never exposed to learners** (evaluator-only reference).
