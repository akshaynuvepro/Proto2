---
name: "Validation Repository Reference"
description: "How to build the _Validation grader: file set, one check per task bullet, marks per check, phase grouping, and result JSON."
---

# Validation Repository Reference

## 🎯 Purpose

Define the **_Validation** grader structure, testcase design, and result JSON format for AWS assessments. The grader runs evaluator-side, checks learner work against exact resource names and expected values, and returns a JSON result with per-testcase pass/fail and marks.

---

## 🧠 Core Principles

- **One check per task bullet**: Every task bullet in the _Main task doc maps to at least one testcase.
- **Marks sum to total**: `sum(testcase.marks) == total_marks` (default 100).
- **Phase grouping**: Testcases are grouped into phases matching the task doc structure.
- **Exact name discipline**: Resource names stated in the task doc MUST match byte-for-byte the names checked by the grader.
- **Evaluator-only**: Never place expected values, answer keys, or solution code into _Main.

---

## 🔥 Recommended Grader Format

**Python harness** (3 of 4 assessments use this):

```
<base>_Validation/
├── grader.py                # main entry point
├── testcases/
│   ├── __init__.py
│   ├── tc01_cloudformation.py
│   ├── tc02_kms.py
│   ├── tc03_secrets.py
│   ├── tc04_dynamodb_s3.py
│   ├── tc05_api_endpoints.py
│   ├── tc06_kms_encrypted_fields.py
│   ├── tc07_secrets_retrieval.py
│   ├── tc08_ecr.py
│   ├── tc09_ecs_alb_apigw.py
│   ├── tc10_pipeline_codebuild.py
│   ├── tc11_codedeploy.py
│   ├── tc12_cloudtrail.py
│   ├── tc13_cloudwatch.py
│   ├── tc14_e2e_pipeline.py
│   ├── tc15_rollback.py
│   └── tc16_security.py
├── utils/
│   ├── __init__.py
│   ├── aws_helpers.py       # boto3 wrappers
│   ├── config.py            # expected values, resource names
│   └── logger.py
├── requirements.txt
└── README.md
```

**Alternative**: JSON testcase manifest + generic runner (1 of 4 assessments).

---

## 📋 Testcase Schema

Each testcase object:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable ID, e.g. `tc01`, `TC001` |
| `name` | string | Human-readable check title |
| `marks` | number | Positive number; all marks sum to `total_marks` |
| `category` | string | Grouping tag: service or capability (e.g. `kms`, `api`, `cloudformation`) |
| `phase` | string | Phase/milestone this check belongs to (matches task doc) |
| `check_kind` | string | `api`, `resource`, `db`, `code`, `e2e` |
| `details` | object | Format-specific fields (see below) |

**Common `details` fields**:

- **API checks**: `endpoint`, `method`, `expectedStatusCode`, `expectedFields`, `authToken`
- **Resource checks**: `resourceType`, `resourceName`, `expectedProperties` (e.g. `{"Encryption": "AES256"}`)
- **DB checks**: `tableName`, `key`, `expectedAttributes`, `encryptedFields`
- **Code checks**: `filePath`, `expectedPatterns`, `forbiddenPatterns`
- **E2E checks**: `workflow`, `expectedOutcome`, `rollbackTrigger`

---

## 🏗️ File Set

### 1. `grader.py` (main entry point)

```python
#!/usr/bin/env python3
import sys
import json
from testcases import (
    tc01_cloudformation, tc02_kms, tc03_secrets, tc04_dynamodb_s3,
    tc05_api_endpoints, tc06_kms_encrypted_fields, tc07_secrets_retrieval,
    tc08_ecr, tc09_ecs_alb_apigw, tc10_pipeline_codebuild, tc11_codedeploy,
    tc12_cloudtrail, tc13_cloudwatch, tc14_e2e_pipeline, tc15_rollback,
    tc16_security
)
from utils.logger import setup_logger

TESTCASES = [
    tc01_cloudformation, tc02_kms, tc03_secrets, tc04_dynamodb_s3,
    tc05_api_endpoints, tc06_kms_encrypted_fields, tc07_secrets_retrieval,
    tc08_ecr, tc09_ecs_alb_apigw, tc10_pipeline_codebuild, tc11_codedeploy,
    tc12_cloudtrail, tc13_cloudwatch, tc14_e2e_pipeline, tc15_rollback,
    tc16_security
]

def main():
    logger = setup_logger()
    results = []
    total_score = 0.0

    for tc_module in TESTCASES:
        try:
            result = tc_module.run()
            results.append(result)
            if result.get("passed"):
                total_score += result.get("marks", 0)
        except Exception as e:
            logger.error(f"Testcase {tc_module.__name__} failed: {e}")
            results.append({
                "id": tc_module.ID,
                "name": tc_module.NAME,
                "passed": False,
                "marks": 0,
                "max_marks": tc_module.MARKS,
                "error": str(e)
            })

    output = {
        "total_score": total_score,
        "max_score": sum(tc.MARKS for tc in TESTCASES),
        "testcases": results
    }

    print(json.dumps(output, indent=2))
    sys.exit(0 if total_score == output["max_score"] else 1)

if __name__ == "__main__":
    main()
```

### 2. `testcases/tc01_cloudformation.py` (example)

```python
import boto3
from utils.config import EXPECTED_STACK_NAME, EXPECTED_RESOURCES

ID = "tc01"
NAME = "CloudFormation stack provisioned with all required resources"
MARKS = 8.0
CATEGORY = "cloudformation"
PHASE = "Phase 1 - Infrastructure Configuration"

def run():
    cfn = boto3.client('cloudformation', region_name='us-east-1')
    
    try:
        stack = cfn.describe_stacks(StackName=EXPECTED_STACK_NAME)['Stacks'][0]
        if stack['StackStatus'] not in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
            return {
                "id": ID, "name": NAME, "passed": False, "marks": 0,
                "max_marks": MARKS, "message": f"Stack status: {stack['StackStatus']}"
            }
        
        resources = cfn.list_stack_resources(StackName=EXPECTED_STACK_NAME)['StackResourceSummaries']
        resource_types = {r['ResourceType'] for r in resources}
        
        missing = set(EXPECTED_RESOURCES) - resource_types
        if missing:
            return {
                "id": ID, "name": NAME, "passed": False, "marks": 0,
                "max_marks": MARKS, "message": f"Missing resources: {missing}"
            }
        
        return {
            "id": ID, "name": NAME, "passed": True, "marks": MARKS,
            "max_marks": MARKS, "message": "Stack provisioned correctly"
        }
    
    except Exception as e:
        return {
            "id": ID, "name": NAME, "passed": False, "marks": 0,
            "max_marks": MARKS, "error": str(e)
        }
```

### 3. `utils/config.py` (expected values)

```python
# CloudFormation
EXPECTED_STACK_NAME = "trade-platform-infra-dev"
EXPECTED_RESOURCES = [
    "AWS::ECS::Cluster",
    "AWS::EC2::VPC",
    "AWS::EC2::Subnet",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::ApiGateway::RestApi",
    "AWS::Cognito::UserPool"
]

# KMS
EXPECTED_KMS_ALIAS = "alias/trade-platform-kms"

# Secrets Manager
EXPECTED_SECRET_NAME = "trade-app-secrets"

# DynamoDB
EXPECTED_TABLE_NAME = "trade-settlement-api"
EXPECTED_TABLE_KEYS = {"tradeId": "S"}

# S3
EXPECTED_BUCKET_PREFIX = "trade-api-bucket-"

# ECR
EXPECTED_ECR_REPO = "trade-settlement-api"

# ECS
EXPECTED_CLUSTER_NAME = "trade-platform-cluster"
EXPECTED_SERVICE_NAME = "trade-api-service"

# CodeDeploy
EXPECTED_APP_NAME = "trade-platform-codedeploy-app"
EXPECTED_DG_NAME = "trade-platform-bluegreen-dg"

# CodePipeline
EXPECTED_PIPELINE_NAME = "trade-platform-cicd-pipeline"

# CloudTrail
EXPECTED_TRAIL_NAME = "trade-platform-trail"

# CloudWatch Alarms
EXPECTED_ALARMS = [
    "trade-api-high-latency",
    "trade-api-5xx-errors",
    "trade-api-unhealthy-hosts",
    "trade-api-green-unhealthy"
]

# API Gateway
API_ENDPOINTS = {
    "POST /trades": {"status": 201, "fields": ["tradeId", "status"]},
    "GET /trades/{tradeId}": {"status": 200, "fields": ["tradeId", "accountId", "status"]},
    "PUT /trades/{tradeId}/status": {"status": 200, "fields": ["tradeId", "status"]}
}
```

### 4. `utils/aws_helpers.py` (boto3 wrappers)

```python
import boto3
from botocore.exceptions import ClientError

def get_stack_status(stack_name, region='us-east-1'):
    cfn = boto3.client('cloudformation', region_name=region)
    try:
        resp = cfn.describe_stacks(StackName=stack_name)
        return resp['Stacks'][0]['StackStatus']
    except ClientError:
        return None

def get_kms_key_by_alias(alias, region='us-east-1'):
    kms = boto3.client('kms', region_name=region)
    try:
        resp = kms.describe_key(KeyId=alias)
        return resp['KeyMetadata']
    except ClientError:
        return None

def get_secret(secret_name, region='us-east-1'):
    sm = boto3.client('secretsmanager', region_name=region)
    try:
        resp = sm.get_secret_value(SecretId=secret_name)
        return resp
    except ClientError:
        return None

def get_parameter(param_name, region='us-east-1'):
    ssm = boto3.client('ssm', region_name=region)
    try:
        resp = ssm.get_parameter(Name=param_name, WithDecryption=True)
        return resp['Parameter']
    except ClientError:
        return None

def get_dynamodb_table(table_name, region='us-east-1'):
    ddb = boto3.client('dynamodb', region_name=region)
    try:
        resp = ddb.describe_table(TableName=table_name)
        return resp['Table']
    except ClientError:
        return None

def get_ecr_images(repo_name, region='us-east-1'):
    ecr = boto3.client('ecr', region_name=region)
    try:
        resp = ecr.describe_images(repositoryName=repo_name)
        return resp['imageDetails']
    except ClientError:
        return []

def get_ecs_service(cluster, service, region='us-east-1'):
    ecs = boto3.client('ecs', region_name=region)
    try:
        resp = ecs.describe_services(cluster=cluster, services=[service])
        return resp['services'][0] if resp['services'] else None
    except ClientError:
        return None

def get_pipeline_state(pipeline_name, region='us-east-1'):
    cp = boto3.client('codepipeline', region_name=region)
    try:
        resp = cp.get_pipeline_state(name=pipeline_name)
        return resp
    except ClientError:
        return None

def get_trail(trail_name, region='us-east-1'):
    ct = boto3.client('cloudtrail', region_name=region)
    try:
        resp = ct.get_trail_status(Name=trail_name)
        return resp
    except ClientError:
        return None

def get_cloudwatch_alarms(alarm_names, region='us-east-1'):
    cw = boto3.client('cloudwatch', region_name=region)
    try:
        resp = cw.describe_alarms(AlarmNames=alarm_names)
        return resp['MetricAlarms']
    except ClientError:
        return []
```

### 5. `requirements.txt`

```
boto3>=1.26.0
requests>=2.28.0
```

### 6. `README.md`

```markdown
# Trade Settlement Platform Validation Grader

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python grader.py
```

## Output

JSON with:
- `total_score`: marks earned
- `max_score`: total marks available
- `testcases`: array of testcase results

Each testcase result:
- `id`, `name`, `passed`, `marks`, `max_marks`, `message` or `error`
```

---

## 🧩 Testcase Grouping by Phase

Map testcases to phases from the task doc:

| Phase | Testcases | Total Marks |
|-------|-----------|-------------|
| Phase 1 - Infrastructure Configuration | tc01–tc04 | 28 |
| Phase 2 - Application Development | tc05–tc07 | 24 |
| Phase 3 - Deployment & Integration (CI/CD) | tc08–tc11 | 30 |
| Phase 4 - Observability & Audit | tc12–tc13 | 8 |
| Phase 5 - End-to-End Validation | tc14–tc16 | 10 |
| **Total** | **16** | **100** |

---

## 📊 Result JSON Format

```json
{
  "total_score": 87.0,
  "max_score": 100.0,
  "testcases": [
    {
      "id": "tc01",
      "name": "CloudFormation stack provisioned with all required resources",
      "passed": true,
      "marks": 8.0,
      "max_marks": 8.0,
      "category": "cloudformation",
      "phase": "Phase 1 - Infrastructure Configuration",
      "message": "Stack provisioned correctly"
    },
    {
      "id": "tc02",
      "name": "KMS key created with correct alias and encryption enabled",
      "passed": true,
      "marks": 6.0,
      "max_marks": 6.0,
      "category": "kms",
      "phase": "Phase 1 - Infrastructure Configuration",
      "message": "KMS key alias/trade-platform-kms found and enabled"
    },
    {
      "id": "tc05",
      "name": "Trade API endpoints return correct status codes and response structure",
      "passed": false,
      "marks": 0.0,
      "max_marks": 10.0,
      "category": "api",
      "phase": "Phase 2 - Application Development",
      "message": "POST /trades returned 500 instead of 201"
    }
  ]
}
```

---

## ⚠️ Strict Rules

- **Do NOT** place expected values, answer keys, or solution code into `<base>_Main`.
- **Do NOT** create testcases that check for resources not explicitly named in the task doc.
- **Do NOT** allow partial credit within a single testcase; each testcase is pass/fail.
- **Do NOT** skip testcases for any task bullet; every bullet must have at least one check.
- **Do NOT** use hardcoded account IDs or region-specific ARNs unless the task doc specifies them.
- **Do NOT** assume resource names; the task doc MUST state them exactly.

---

## 📌 Output Expectations

1. **File set**: `grader.py`, `testcases/*.py`, `utils/*.py`, `requirements.txt`, `README.md`.
2. **Testcase modules**: One `.py` file per testcase, each exporting `ID`, `NAME`, `MARKS`, `CATEGORY`, `PHASE`, and `run()`.
3. **Config file**: `utils/config.py` with all expected resource names and values.
4. **Result JSON**: `total_score`, `max_score`, `testcases` array.
5. **Marks sum**: `sum(testcase.marks) == total_marks`.
6. **
