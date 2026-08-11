"""Assessment + curated AWS knowledge tools for compare/improve agents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from sacrebleu.metrics import BLEU

from .models import Assessment, SkillPackage

# --- curated offline AWS snippets (no live AWS account) ---

AWS_SERVICES: dict[str, str] = {
    "s3": (
        "Amazon S3: object storage with buckets/keys, versioning, lifecycle, "
        "encryption (SSE-S3/KMS), IAM bucket policies, EventBridge/S3 events. "
        "Labs often cover upload/download, CORS, static hosting, or data lakes."
    ),
    "eks": (
        "Amazon EKS: managed Kubernetes control plane. Common lab themes: "
        "cluster/node groups, IAM roles for service accounts (IRSA), ALB Ingress, "
        "kubectl deploy, CloudWatch Container Insights."
    ),
    "ecs": (
        "Amazon ECS: container orchestration (Fargate/EC2 launch types), task "
        "definitions, services, ALB target groups, IAM task roles, CloudWatch logs."
    ),
    "lambda": (
        "AWS Lambda: serverless functions, event sources (API GW, S3, SQS, "
        "EventBridge), IAM execution role, layers, concurrency, CloudWatch logs."
    ),
    "iam": (
        "AWS IAM: users/roles/policies, least privilege, trust policies, "
        "permission boundaries, STS assume-role. Assessments should stress "
        "scoped policies over admin*."
    ),
    "kinesis": (
        "Amazon Kinesis Data Streams: real-time ingest, shards, producers/"
        "consumers, enhanced fan-out, integration with Lambda/Firehose."
    ),
    "dynamodb": (
        "Amazon DynamoDB: NoSQL key-value/document, partition/sort keys, GSIs, "
        "on-demand vs provisioned, Streams, TTL, IAM condition keys."
    ),
    "cloudformation": (
        "AWS CloudFormation: IaC templates (YAML/JSON), stacks, parameters, "
        "outputs, nested stacks, drift. Labs often create/update/delete stacks."
    ),
    "codepipeline": (
        "AWS CodePipeline: CI/CD stages (Source/Build/Deploy), CodeBuild, "
        "CodeDeploy, artifact buckets, IAM roles for pipeline actions."
    ),
    "ec2": (
        "Amazon EC2: instances, AMIs, security groups, key pairs, EBS, "
        "user-data. Prefer least-open SG rules in assessments."
    ),
    "rds": (
        "Amazon RDS: managed relational DB, Multi-AZ, snapshots, parameter "
        "groups, security groups, encryption at rest."
    ),
    "vpc": (
        "Amazon VPC: subnets, route tables, IGW/NAT, security groups vs NACLs, "
        "endpoints. Labs often wire private apps to public ALB."
    ),
    "cloudwatch": (
        "Amazon CloudWatch: metrics, alarms, logs, dashboards. Assessments "
        "should include observability acceptance criteria."
    ),
    "api gateway": (
        "Amazon API Gateway: REST/HTTP APIs, Lambda proxy, auth (IAM/JWT/Cognito), "
        "throttling, stages."
    ),
    "sqs": (
        "Amazon SQS: queues, visibility timeout, DLQ, FIFO vs standard, "
        "Lambda event source mapping."
    ),
}

WA_SNIPPETS: list[dict[str, str]] = [
    {
        "pillar": "Operational Excellence",
        "id": "ops-1",
        "text": "Define runbooks and measurable outcomes; include CloudWatch alarms and rollback steps in labs.",
    },
    {
        "pillar": "Security",
        "id": "sec-1",
        "text": "Least-privilege IAM, encryption in transit/at rest, no long-lived keys in code, SG least open.",
    },
    {
        "pillar": "Reliability",
        "id": "rel-1",
        "text": "Multi-AZ where relevant, health checks, retries/backoff, clear failure modes and recovery.",
    },
    {
        "pillar": "Performance Efficiency",
        "id": "perf-1",
        "text": "Right-size compute, caching, async where latency allows; avoid over-provisioned defaults.",
    },
    {
        "pillar": "Cost Optimization",
        "id": "cost-1",
        "text": "Prefer serverless/spot when fit; lifecycle policies; tear-down steps so labs do not leak spend.",
    },
    {
        "pillar": "Sustainability",
        "id": "sus-1",
        "text": "Minimize idle resources; use managed services; clean up lab stacks after validation.",
    },
    {
        "pillar": "Assessment craft",
        "id": "asm-1",
        "text": "SME labs: timed phases, concrete resource names, measurable 'done when', not tutorial prose.",
    },
    {
        "pillar": "Assessment craft",
        "id": "asm-2",
        "text": "Avoid 'What You Will Learn' course tone; prefer scenario, tasks, validation, cleanup.",
    },
]

_DURATION_RE = re.compile(
    r"\b(\d+\s*[-–]?\s*\d*\s*(minutes?|mins?|hours?|hrs?)|duration\s*:)\b",
    re.I,
)
_PHASE_RE = re.compile(
    r"(?m)^(#{1,3}\s+.*(phase|task|step|lab|part)\b|\*\*(phase|task|step)\s*\d+)",
    re.I,
)
_RESOURCE_RE = re.compile(
    r"\b(arn:aws:[a-z0-9-]+:|i-[0-9a-f]{8,}|sg-[0-9a-f]+|subnet-[0-9a-f]+|"
    r"vpc-[0-9a-f]+|bucket|cluster|stack|role|policy|queue|table)\b",
    re.I,
)
_LEARN_RE = re.compile(r"what you will learn|in this lab you will learn|learning objectives", re.I)
_HEADING_RE = re.compile(r"(?m)^#{1,3}\s+\S+")


@dataclass
class ToolContext:
    generated: list[Assessment] = field(default_factory=list)
    holdout: list[Assessment] = field(default_factory=list)
    skill: SkillPackage | None = None
    report: dict[str, Any] | None = None
    improver_md: str = ""

    def _pool(self, source: str | None) -> list[Assessment]:
        src = (source or "all").lower()
        if src == "generated":
            return self.generated
        if src in ("holdout", "sme"):
            return self.holdout
        return [*self.holdout, *self.generated]

    def find(self, assessment_id: str) -> Assessment | None:
        for a in (*self.holdout, *self.generated):
            if a.id == assessment_id:
                return a
        return None


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def tool_definitions(*, include_report: bool = False, include_improver: bool = False) -> list[dict[str, Any]]:
    defs = [
        _tool(
            "list_assessments",
            "List assessment ids and titles for generated and/or holdout sets.",
            {
                "source": {
                    "type": "string",
                    "enum": ["generated", "holdout", "all"],
                    "description": "Which set to list (default all).",
                }
            },
        ),
        _tool(
            "get_assessment",
            "Fetch full assessment body by id.",
            {"id": {"type": "string", "description": "Assessment id"}},
            ["id"],
        ),
        _tool(
            "get_skill_file",
            "Read a file from the current skill package by path (e.g. SKILL.md).",
            {
                "path": {"type": "string", "description": "File path inside the skill package"},
                "max_chars": {"type": "integer", "description": "Optional truncate length"},
            },
            ["path"],
        ),
        _tool(
            "run_structure_check",
            "Heuristic structure checks on an assessment (duration, phases, resources, tutorial tone).",
            {"id": {"type": "string", "description": "Assessment id"}},
            ["id"],
        ),
        _tool(
            "lookup_aws_service",
            "Curated offline snippet for a common AWS service (S3, EKS, Lambda, IAM, …).",
            {"service": {"type": "string", "description": "Service name or short code"}},
            ["service"],
        ),
        _tool(
            "search_aws_wellarchitected",
            "Search curated Well-Architected / assessment-craft snippets.",
            {"query": {"type": "string", "description": "Keywords e.g. security, IAM, cleanup"}},
            ["query"],
        ),
        _tool(
            "compute_text_overlap",
            "Cheap BLEU sentence score between two assessments by id.",
            {
                "generated_id": {"type": "string"},
                "holdout_id": {"type": "string"},
            },
            ["generated_id", "holdout_id"],
        ),
        _tool(
            "fetch_aws_doc_hint",
            "Fetch a short public AWS docs page by exact docs.aws.amazon.com path (optional; may fail offline).",
            {
                "path": {
                    "type": "string",
                    "description": "Path under docs.aws.amazon.com, e.g. AmazonS3/latest/userguide/Welcome.html",
                }
            },
            ["path"],
        ),
    ]
    if include_report:
        defs.append(
            _tool(
                "get_comparison_report",
                "Read prior comparison report summary, scores, and priority_fixes.",
                {
                    "section": {
                        "type": "string",
                        "enum": ["summary", "priority_fixes", "dimensions", "improvement_brief", "all"],
                    }
                },
            )
        )
    if include_improver:
        defs.append(
            _tool(
                "get_improver_skill",
                "Read the IMPROVER_SKILL.md markdown currently being applied.",
                {"max_chars": {"type": "integer"}},
            )
        )
    return defs


def make_handlers(ctx: ToolContext) -> dict[str, Any]:
    def list_assessments(args: dict[str, Any]) -> Any:
        items = ctx._pool(args.get("source"))
        return [{"id": a.id, "title": a.title, "source": a.source, "chars": len(a.body)} for a in items]

    def get_assessment(args: dict[str, Any]) -> Any:
        a = ctx.find(str(args.get("id") or ""))
        if not a:
            return {"error": "not found"}
        body = a.body
        if len(body) > 20_000:
            body = body[:20_000] + "\n...[truncated]"
        return {"id": a.id, "title": a.title, "source": a.source, "body": body}

    def get_skill_file(args: dict[str, Any]) -> Any:
        if not ctx.skill:
            return {"error": "no skill package loaded"}
        path = str(args.get("path") or "")
        content = ctx.skill.files.get(path)
        if content is None:
            return {"error": "not found", "available": sorted(ctx.skill.files)}
        max_chars = int(args.get("max_chars") or 12_000)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[truncated]"
        return {"path": path, "content": content}

    def get_comparison_report(args: dict[str, Any]) -> Any:
        if not ctx.report:
            return {"error": "no comparison report loaded"}
        section = str(args.get("section") or "all")
        r = ctx.report
        if section == "summary":
            return {"summary_markdown": r.get("summary_markdown"), "overall_score": r.get("overall_score")}
        if section == "priority_fixes":
            return {"priority_fixes": r.get("priority_fixes")}
        if section == "dimensions":
            return {"dimensions": r.get("dimensions")}
        if section == "improvement_brief":
            return {"improvement_brief": r.get("improvement_brief")}
        return {
            "overall_score": r.get("overall_score"),
            "dimensions": r.get("dimensions"),
            "priority_fixes": r.get("priority_fixes"),
            "improvement_brief": r.get("improvement_brief"),
            "summary_markdown": (r.get("summary_markdown") or "")[:8000],
            "pairs": r.get("pairs"),
        }

    def get_improver_skill(args: dict[str, Any]) -> Any:
        if not ctx.improver_md:
            return {"error": "no improver skill loaded"}
        max_chars = int(args.get("max_chars") or 16_000)
        text = ctx.improver_md
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[truncated]"
        return {"content": text}

    def run_structure_check(args: dict[str, Any]) -> Any:
        a = ctx.find(str(args.get("id") or ""))
        if not a:
            return {"error": "not found"}
        text = f"{a.title}\n{a.body}"
        findings: list[dict[str, Any]] = []

        has_duration = bool(_DURATION_RE.search(text))
        findings.append(
            {
                "check": "duration_present",
                "ok": has_duration,
                "detail": "Found duration/time language" if has_duration else "No clear duration/minutes language",
            }
        )

        phases = _PHASE_RE.findall(text)
        headings = _HEADING_RE.findall(text)
        findings.append(
            {
                "check": "phases_or_headings",
                "ok": len(phases) >= 2 or len(headings) >= 3,
                "detail": f"phase-like={len(phases)} headings={len(headings)}",
            }
        )

        resources = _RESOURCE_RE.findall(text)
        density = len(resources) / max(1, len(text.split()))
        findings.append(
            {
                "check": "resource_naming_density",
                "ok": len(resources) >= 3,
                "detail": f"matches={len(resources)} density={density:.4f}",
            }
        )

        tutorial = bool(_LEARN_RE.search(text))
        findings.append(
            {
                "check": "tutorial_tone",
                "ok": not tutorial,
                "detail": "Found 'What You Will Learn'/course tone" if tutorial else "No tutorial course-tone markers",
            }
        )

        passed = sum(1 for f in findings if f["ok"])
        return {
            "id": a.id,
            "title": a.title,
            "passed": passed,
            "total": len(findings),
            "findings": findings,
        }

    def lookup_aws_service(args: dict[str, Any]) -> Any:
        raw = str(args.get("service") or "").strip().lower()
        key = re.sub(r"[^a-z0-9]+", " ", raw).strip()
        aliases = {
            "amazon s3": "s3",
            "simple storage": "s3",
            "elastic kubernetes service": "eks",
            "elastic container service": "ecs",
            "api-gateway": "api gateway",
            "apigateway": "api gateway",
            "ddb": "dynamodb",
            "cfn": "cloudformation",
        }
        key = aliases.get(key, key)
        if key in AWS_SERVICES:
            return {"service": key, "snippet": AWS_SERVICES[key]}
        # fuzzy: substring match
        for k, v in AWS_SERVICES.items():
            if k in key or key in k:
                return {"service": k, "snippet": v}
        return {"error": "unknown service", "known": sorted(AWS_SERVICES)}

    def search_aws_wellarchitected(args: dict[str, Any]) -> Any:
        q = str(args.get("query") or "").strip().lower()
        tokens = [t for t in re.split(r"\W+", q) if t]
        scored: list[tuple[int, dict[str, str]]] = []
        for snip in WA_SNIPPETS:
            blob = f"{snip['pillar']} {snip['text']}".lower()
            score = sum(1 for t in tokens if t in blob) if tokens else 1
            if score:
                scored.append((score, snip))
        scored.sort(key=lambda x: -x[0])
        hits = [s for _, s in scored[:5]]
        return {"query": q, "hits": hits or WA_SNIPPETS[:3]}

    def compute_text_overlap(args: dict[str, Any]) -> Any:
        g = ctx.find(str(args.get("generated_id") or ""))
        h = ctx.find(str(args.get("holdout_id") or ""))
        if not g or not h:
            return {"error": "need valid generated_id and holdout_id"}
        bleu = BLEU(effective_order=True)
        hyp = f"{g.title}\n{g.body}"
        ref = f"{h.title}\n{h.body}"
        score = float(bleu.sentence_score(hyp, [ref]).score)
        return {
            "generated_id": g.id,
            "holdout_id": h.id,
            "bleu": round(score, 4),
        }

    def fetch_aws_doc_hint(args: dict[str, Any]) -> Any:
        # ponytail: optional network; fail soft — agents must work offline
        path = str(args.get("path") or "").lstrip("/")
        if ".." in path or path.startswith("http"):
            return {"error": "pass a relative docs.aws.amazon.com path only"}
        url = f"https://docs.aws.amazon.com/{path}"
        try:
            with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "skill-lab/1.0"})
            if resp.status_code >= 400:
                return {"error": f"HTTP {resp.status_code}", "url": url}
            text = resp.text
            # strip tags lightly
            text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
            text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return {"url": url, "hint": text[:4000]}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "url": url}

    return {
        "list_assessments": list_assessments,
        "get_assessment": get_assessment,
        "get_skill_file": get_skill_file,
        "get_comparison_report": get_comparison_report,
        "get_improver_skill": get_improver_skill,
        "run_structure_check": run_structure_check,
        "lookup_aws_service": lookup_aws_service,
        "search_aws_wellarchitected": search_aws_wellarchitected,
        "compute_text_overlap": compute_text_overlap,
        "fetch_aws_doc_hint": fetch_aws_doc_hint,
    }
