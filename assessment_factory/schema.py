"""Canonical, versioned data contracts for the assessment factory."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def content_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest[:20]}"


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return text.strip("-") or "item"


class SchemaError(ValueError):
    """Raised when a record violates its contract."""


# --------------------------------------------------------------------------
# canonical assessment record
# --------------------------------------------------------------------------

@dataclass
class TestCase:
    """One gradable check, normalized across every source format."""

    test_id: str
    name: str
    marks: float
    category: str = ""
    phase: str = ""
    check_kind: str = ""          # api | resource | db | code | e2e | unknown
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TestCase":
        return cls(
            test_id=str(raw.get("test_id") or raw.get("id") or ""),
            name=str(raw.get("name") or ""),
            marks=float(raw.get("marks") or 0),
            category=str(raw.get("category") or ""),
            phase=str(raw.get("phase") or ""),
            check_kind=str(raw.get("check_kind") or ""),
            details=dict(raw.get("details") or {}),
        )


@dataclass
class Phase:
    name: str
    objective: str = ""
    tasks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Phase":
        return cls(
            name=str(raw.get("name") or ""),
            objective=str(raw.get("objective") or ""),
            tasks=[str(t) for t in (raw.get("tasks") or [])],
        )


@dataclass
class AssessmentRecord:
    """One normalized assessment or guided project (source-format agnostic)."""

    SCHEMA = "assessment-record/1"

    record_id: str
    base_repo: str
    content_type: str = "assessment"       # assessment | guided_project
    domain: str = "aws"
    title: str = ""
    duration_minutes: int | None = None
    scenario: str = ""
    services: list[str] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    resource_registry: list[str] = field(default_factory=list)
    testcases: list[TestCase] = field(default_factory=list)
    total_marks: float = 0.0
    grader_format: str = "none"            # python_harness | json_testcases | doc_only | none
    deliverables: list[dict[str, Any]] = field(default_factory=list)
    technical_requirements: list[dict[str, Any]] = field(default_factory=list)
    business_rules: list[dict[str, Any]] = field(default_factory=list)
    tech_stack: dict[str, Any] = field(default_factory=dict)
    has_solution: bool = False
    has_validation: bool = False
    main_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA
    content_hash: str = ""

    def finalize(self) -> "AssessmentRecord":
        raw = self.to_dict()
        raw["content_hash"] = ""
        self.content_hash = content_hash(raw)
        return self

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["phases"] = [p.to_dict() for p in self.phases]
        data["testcases"] = [t.to_dict() for t in self.testcases]
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AssessmentRecord":
        record = cls(
            record_id=str(raw["record_id"]),
            base_repo=str(raw.get("base_repo") or ""),
            content_type=str(raw.get("content_type") or "assessment"),
            domain=str(raw.get("domain") or "aws"),
            title=str(raw.get("title") or ""),
            duration_minutes=raw.get("duration_minutes"),
            scenario=str(raw.get("scenario") or ""),
            services=[str(s) for s in (raw.get("services") or [])],
            phases=[Phase.from_dict(p) for p in (raw.get("phases") or [])],
            resource_registry=[str(r) for r in (raw.get("resource_registry") or [])],
            testcases=[TestCase.from_dict(t) for t in (raw.get("testcases") or [])],
            total_marks=float(raw.get("total_marks") or 0),
            grader_format=str(raw.get("grader_format") or "none"),
            deliverables=list(raw.get("deliverables") or []),
            technical_requirements=list(raw.get("technical_requirements") or []),
            business_rules=list(raw.get("business_rules") or []),
            tech_stack=dict(raw.get("tech_stack") or {}),
            has_solution=bool(raw.get("has_solution")),
            has_validation=bool(raw.get("has_validation")),
            main_files=[str(f) for f in (raw.get("main_files") or [])],
            warnings=[str(w) for w in (raw.get("warnings") or [])],
            source=dict(raw.get("source") or {}),
            created_at=str(raw.get("created_at") or utc_now()),
            schema_version=str(raw.get("schema_version") or cls.SCHEMA),
            content_hash=str(raw.get("content_hash") or ""),
        )
        return record


# --------------------------------------------------------------------------
# template
# --------------------------------------------------------------------------

@dataclass
class Template:
    """House-style blueprint distilled from one or more records."""

    SCHEMA = "assessment-template/1"

    template_id: str
    name: str
    domain: str = "aws"
    content_type: str = "assessment"
    status: str = "draft"                  # draft | approved | rejected
    structure: dict[str, Any] = field(default_factory=dict)
    house_style: dict[str, Any] = field(default_factory=dict)
    testcase_schema: dict[str, Any] = field(default_factory=dict)
    derived_from: list[str] = field(default_factory=list)
    canonical_example: dict[str, Any] = field(default_factory=dict)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA
    content_hash: str = ""

    def finalize(self) -> "Template":
        raw = asdict(self)
        raw["content_hash"] = ""
        self.content_hash = content_hash(raw)
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Template":
        return cls(
            template_id=str(raw["template_id"]),
            name=str(raw.get("name") or ""),
            domain=str(raw.get("domain") or "aws"),
            content_type=str(raw.get("content_type") or "assessment"),
            status=str(raw.get("status") or "draft"),
            structure=dict(raw.get("structure") or {}),
            house_style=dict(raw.get("house_style") or {}),
            testcase_schema=dict(raw.get("testcase_schema") or {}),
            derived_from=[str(r) for r in (raw.get("derived_from") or [])],
            canonical_example=dict(raw.get("canonical_example") or {}),
            reviews=list(raw.get("reviews") or []),
            created_at=str(raw.get("created_at") or utc_now()),
            schema_version=str(raw.get("schema_version") or cls.SCHEMA),
            content_hash=str(raw.get("content_hash") or ""),
        )


# --------------------------------------------------------------------------
# skill file
# --------------------------------------------------------------------------

@dataclass
class SkillFile:
    """A structured skill *package*: multiple files (SKILL.md + references + scripts).

    ``files`` maps a relative path (e.g. ``references/main-repo.md``) to its text
    content. ``entry`` is the router file an agent reads first.
    """

    SCHEMA = "assessment-skill/2"

    skill_id: str
    name: str
    template_id: str
    domain: str = "aws"
    content_type: str = "assessment"
    status: str = "draft"                  # draft | approved | rejected
    entry: str = "SKILL.md"
    files: dict[str, str] = field(default_factory=dict)
    model_ref: dict[str, Any] = field(default_factory=dict)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA
    content_hash: str = ""

    @property
    def markdown(self) -> str:
        return self.files.get(self.entry, "")

    def finalize(self) -> "SkillFile":
        raw = self.to_dict()
        raw["content_hash"] = ""
        self.content_hash = content_hash(raw)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skill_id": self.skill_id,
            "name": self.name,
            "template_id": self.template_id,
            "domain": self.domain,
            "content_type": self.content_type,
            "status": self.status,
            "entry": self.entry,
            "files": dict(self.files),
            "model_ref": dict(self.model_ref),
            "reviews": list(self.reviews),
            "created_at": self.created_at,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SkillFile":
        # tolerate v1 (single markdown) records
        files = dict(raw.get("files") or {})
        if not files and raw.get("markdown"):
            files = {"SKILL.md": str(raw.get("markdown"))}
        return cls(
            skill_id=str(raw["skill_id"]),
            name=str(raw.get("name") or ""),
            template_id=str(raw.get("template_id") or ""),
            domain=str(raw.get("domain") or "aws"),
            content_type=str(raw.get("content_type") or "assessment"),
            status=str(raw.get("status") or "draft"),
            entry=str(raw.get("entry") or "SKILL.md"),
            files=files,
            model_ref=dict(raw.get("model_ref") or {}),
            reviews=list(raw.get("reviews") or []),
            created_at=str(raw.get("created_at") or utc_now()),
            schema_version=str(raw.get("schema_version") or cls.SCHEMA),
            content_hash=str(raw.get("content_hash") or ""),
        )
