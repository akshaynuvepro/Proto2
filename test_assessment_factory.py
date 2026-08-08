"""Offline tests for the assessment factory (no network, no model)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assessment_factory.github_source import ClonedTriplet, base_name, group_triplets
from assessment_factory.normalize import normalize_triplet
from assessment_factory.skill import compile_skill
from assessment_factory.store import FactoryStore
from assessment_factory.template import build_template


TASK_DOC = """# Sample Cloud Platform Assessment

### Duration
- **Total:** 75 minutes

## Scenario

A firm is modernizing its platform on AWS using Amazon S3, AWS Lambda, and Amazon DynamoDB.

# Phase 1 - Infrastructure Configuration

## Objective
Provision core infrastructure.

## Tasks
1. Create an S3 bucket named **trade-api-bucket-dev**.
2. Create a KMS key with alias **trade-platform-kms**.

# Phase 2 - Application Development

## Objective
Complete the API.

## Tasks
1. Implement the controller.

# Testcases

## Phase 1 - Infrastructure Configuration
- Validate CloudFormation provisioning. **(Marks = 8)**
- Validate KMS key creation. **(Marks = 6)**

## Phase 2 - Application Development
- Validate API endpoints. **(Marks = 10)**
"""

HARNESS = '''
REGION = "us-east-1"
KMS_ALIAS_NAME = "alias/trade-platform-kms"
S3_SOURCE_BUCKET_PREFIX = "trade-api-bucket-"

TESTCASE_MARKS = {
    "testcase1_cloudformation_stack": 8,
    "testcase2_kms_key": 6,
    "testcase3_trade_api_endpoints": 10,
}

class T:
    def _define_milestones(self):
        self.add_milestone("Phase 1 - Infrastructure Configuration", ["testcase1_cloudformation_stack", "testcase2_kms_key"])
        self.add_milestone("Phase 2 - Application Development", ["testcase3_trade_api_endpoints"])
    def testcase1_cloudformation_stack(self): pass
    def testcase2_kms_key(self): pass
    def testcase3_trade_api_endpoints(self): pass
'''


def _make_triplet(root: Path, base: str = "AWS-Sample-Assessment-AP") -> ClonedTriplet:
    main = root / base / "Main"
    validation = root / base / "Validation"
    (main).mkdir(parents=True)
    (validation).mkdir(parents=True)
    (main / "Assessment-Activities.md").write_text(TASK_DOC, encoding="utf-8")
    (validation / "test_cases.py").write_text(HARNESS, encoding="utf-8")
    return ClonedTriplet(base=base, org="test-org", main_dir=main, validation_dir=validation,
                         solution_dir=None, missing=["Solution"])


class NormalizeTests(unittest.TestCase):
    def test_base_name_and_grouping(self):
        self.assertEqual(base_name("Foo-Bar-AP_Main"), "Foo-Bar-AP")
        groups = group_triplets(["X_Main", "X_Validation", "Y_Main"])
        self.assertEqual(set(groups["X"].keys()), {"main", "validation"})
        self.assertIn("main", groups["Y"])

    def test_normalize_reads_doc_and_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = normalize_triplet(_make_triplet(Path(tmp)))
        self.assertEqual(record.content_type, "assessment")
        self.assertEqual(record.grader_format, "python_harness")
        self.assertEqual(len(record.testcases), 3)
        self.assertEqual(record.total_marks, 24)
        self.assertEqual(record.duration_minutes, 75)
        self.assertTrue(record.has_validation)
        self.assertFalse(record.has_solution)
        self.assertTrue(any("s3" in s.lower() or "lambda" in s.lower() for s in record.services))
        self.assertIn("trade-platform-kms", record.resource_registry)
        self.assertEqual(len(record.phases), 2)

    def test_doc_only_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "B" / "Main"
            main.mkdir(parents=True)
            (main / "Assessment-Activities.md").write_text(TASK_DOC, encoding="utf-8")
            triplet = ClonedTriplet(base="B", org="o", main_dir=main, missing=["Solution", "Validation"])
            record = normalize_triplet(triplet)
        self.assertEqual(record.grader_format, "doc_only")
        self.assertEqual(record.total_marks, 24)


class TemplateAndSkillTests(unittest.TestCase):
    def _record(self, tmp: str):
        return normalize_triplet(_make_triplet(Path(tmp)))

    def test_template_build_and_house_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._record(tmp)
            template = build_template([record], name="AWS Developer Associate")
        self.assertEqual(template.status, "ready")
        self.assertEqual(template.house_style["total_marks"]["default"], 24)
        self.assertIn("recommended_grader_format", template.structure)
        self.assertEqual(template.derived_from, [record.record_id])

    def test_skill_is_multifile_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._record(tmp)
            template = build_template([record], name="AWS DA")
            skill = compile_skill(template, example=record)
        self.assertEqual(skill.status, "ready")
        # multiple structured files
        self.assertIn("SKILL.md", skill.files)
        self.assertIn("references/main-repo.md", skill.files)
        self.assertIn("references/solution-repo.md", skill.files)
        self.assertIn("references/validation-repo.md", skill.files)
        self.assertIn("scripts/check_consistency.py", skill.files)
        self.assertGreaterEqual(len(skill.files), 6)
        # entry + hard rules present
        self.assertIn("Workflow", skill.markdown)
        self.assertIn("consistency", skill.files["references/testcase-and-marks.md"].lower())
        self.assertEqual(skill.template_id, template.template_id)

    def test_store_roundtrip_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FactoryStore(Path(tmp) / "data")
            record = self._record(tmp)
            store.put_record(record)
            self.assertEqual(len(store.list_records()), 1)
            template = build_template([record], name="AWS DA")
            store.put_template(template)
            skill = compile_skill(store.get_template(template.template_id), example=record)
            store.put_skill(skill)
            self.assertEqual(len(store.list_skills()), 1)
            # package materialized as a directory with real files
            pkg = store.root / "skills" / skill.skill_id
            self.assertTrue((pkg / "SKILL.md").exists())
            self.assertTrue((pkg / "references" / "main-repo.md").exists())
            self.assertTrue((pkg / "scripts" / "check_consistency.py").exists())
            reloaded = store.get_skill(skill.skill_id)
            self.assertEqual(set(reloaded.files.keys()), set(skill.files.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
