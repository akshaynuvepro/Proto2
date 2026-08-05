"""Stdlib assert-based self-checks for skills.py + classify.py. Run: uv run python test_skills.py"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

import classify
import extract_local
import skills


def test_slugify_and_next_free_slug() -> None:
    assert skills.slugify("MediBuddy Health!!") == "medibuddy-health"
    assert skills.slugify("  Weird   Spacing_here  ") == "weird-spacing-here"

    tmp = Path(tempfile.mkdtemp())
    try:
        assert skills.next_free_slug(tmp, "foo") == "foo"
        skills.skill_dir(tmp, "foo").mkdir()
        assert skills.next_free_slug(tmp, "foo") == "foo-2"
        skills.skill_dir(tmp, "foo-2").mkdir()
        assert skills.next_free_slug(tmp, "foo") == "foo-3"
    finally:
        shutil.rmtree(tmp)


def test_render_parse_round_trip() -> None:
    md = skills.render_skill_md(
        name="MediBuddy Health",
        slug="medibuddy-health",
        description='Assesses health plans. Use when a "health" sandbox is requested',
        body_markdown="## When to use\nUse for MediBuddy health.\n\n## What this sandbox is\nsome body text\n",
        created_at="2026-08-04T00:00:00",
        updated_at="2026-08-04T00:00:00",
        session_count=113,
        last_active_date="2026-08-04",
        triggers=["MediBuddy Health Plan Advisor", "rank MediBuddy plans"],
        tags=["medibuddy", "health-insurance"],
        tools=["check_eligibility_coverage"],
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        path = skills.skill_md_path(tmp, "medibuddy-health")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")

        result = skills.read_skill_body(path)
        assert result is not None
        frontmatter, body = result
        assert frontmatter["name"] == "medibuddy-health"
        assert frontmatter["display_name"] == "MediBuddy Health"
        assert frontmatter["slug"] == "medibuddy-health"
        assert frontmatter["session_count"] == 113
        assert 'Use when a "health" sandbox' in frontmatter["description"]
        assert frontmatter["triggers"] == ["MediBuddy Health Plan Advisor", "rank MediBuddy plans"]
        assert frontmatter["tags"] == ["medibuddy", "health-insurance"]
        assert frontmatter["tools"] == ["check_eligibility_coverage"]
        assert "some body text" in body

        skills.write_scripts(tmp, "medibuddy-health", {"validate_output.py": "print('ok')\n"})
        assert "validate_output.py" in skills.read_scripts(tmp, "medibuddy-health")
        catalog = skills.write_catalog(tmp)
        data = json.loads(catalog.read_text(encoding="utf-8"))
        assert data["schema"] == "proto2-skill-catalog/1"
        assert data["skills"][0]["name"] == "medibuddy-health"

        assert skills.read_skill_body(tmp / "nonexistent" / "SKILL.md") is None
    finally:
        shutil.rmtree(tmp)


def test_analysis_skill_round_trip() -> None:
    md = skills.render_analysis_skill_md(
        sandbox_name="MediBuddy Health",
        slug="medibuddy-health",
        instructions_body="Watch for X.\nAlways check Y.",
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        path = skills.analysis_skill_md_path(tmp, "medibuddy-health")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")

        result = skills.read_skill_body(path)
        assert result is not None
        frontmatter, body = result
        assert frontmatter["name"] == "medibuddy-health-analysis"
        assert frontmatter["display_name"] == "MediBuddy Health - Analysis Instructions"
        assert "Watch for X." in body
    finally:
        shutil.rmtree(tmp)


def test_references_round_trip() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        assert skills.read_references(tmp, "foo") == {}
        skills.write_references(tmp, "foo", {"output-contract": "# Output Contract\n...", "glossary": "# Glossary\n..."})
        refs = skills.read_references(tmp, "foo")
        assert set(refs) == {"output-contract", "glossary"}
        assert "Output Contract" in refs["output-contract"]

        skills.write_references(tmp, "foo", {"glossary": "# Glossary\nupdated"})
        refs = skills.read_references(tmp, "foo")
        assert set(refs) == {"glossary"}
        assert "updated" in refs["glossary"]

        skills.write_references(tmp, "foo", {})
        assert skills.read_references(tmp, "foo") == {}
    finally:
        shutil.rmtree(tmp)


def test_session_signature() -> None:
    a = "Hello World, this is the SYSTEM prompt."
    b = "  hello   world,   this is the system prompt.  "
    assert classify.session_signature(a) == classify.session_signature(b)
    assert classify.session_signature(a) != classify.session_signature("something else entirely")


def test_group_digests() -> None:
    digests = [
        {"session_id": "s1", "signature": "sig-a", "sample": "text a", "source_tool": "langsmith"},
        {"session_id": "s2", "signature": "sig-a", "sample": "text a", "source_tool": "langsmith"},
        {"session_id": "s3", "signature": "sig-b", "sample": "text b", "source_tool": "claude"},
    ]
    groups = classify.group_digests(digests)
    assert set(groups) == {"sig-a", "sig-b"}
    assert sorted(groups["sig-a"]["session_ids"]) == ["s1", "s2"]
    assert groups["sig-b"]["session_ids"] == ["s3"]
    assert groups["sig-b"]["source_tool"] == "claude"


def test_build_session_digests_system_and_user() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        langsmith = tmp / "langsmith"
        local = tmp / "local"
        langsmith.mkdir()
        local.mkdir()
        (langsmith / "a.md").write_text(
            "---\nsession_id: \"a\"\nsource: \"langsmith\"\nsource_tool: \"langsmith\"\n---\n\n"
            "## Transcript\n\n[1] SYSTEM:\nYou are MediBuddy.\n\n[2] USER:\nHi\n",
            encoding="utf-8",
        )
        (local / "claude_s1.md").write_text(
            "---\nsession_id: \"claude_s1\"\nsource: \"claude\"\nsource_tool: \"claude\"\n---\n\n"
            "## Transcript\n\n[1] USER:\nFix the login bug\n\n[2] ASSISTANT:\nSure\n",
            encoding="utf-8",
        )
        digests = classify.build_session_digests([langsmith, local])
        assert len(digests) == 2
        by_id = {d["session_id"]: d for d in digests}
        assert by_id["a"]["source_tool"] == "langsmith"
        assert by_id["claude_s1"]["source_tool"] == "claude"
        # Different sources with different openers must not share a signature.
        assert by_id["a"]["signature"] != by_id["claude_s1"]["signature"]
    finally:
        shutil.rmtree(tmp)


def test_extract_local_from_store() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        store = tmp / "conversations.json"
        store.write_text(
            json.dumps(
                {
                    "schema": "proto-capture-conversations/1",
                    "messages": [
                        {
                            "id": "1",
                            "ts": "2026-08-05T10:00:00.000Z",
                            "day": "2026-08-05",
                            "tool": "claude",
                            "sessionId": "sess-1",
                            "role": "user",
                            "text": "hello from coding agent",
                            "source": "live",
                        },
                        {
                            "id": "2",
                            "ts": "2026-08-05T10:00:01.000Z",
                            "day": "2026-08-05",
                            "tool": "claude",
                            "sessionId": "sess-1",
                            "role": "assistant",
                            "text": "hi back",
                            "source": "live",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        out_root = tmp / "out"
        out_dir, count = extract_local.write_local_conversations(
            day=date(2026, 8, 5),
            output_root=out_root,
            store=store,
            force=True,
        )
        assert count == 1
        md = (out_dir / "claude_sess-1.md").read_text(encoding="utf-8")
        assert 'source: "claude"' in md
        assert "hello from coding agent" in md
        assert "hi back" in md
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    test_slugify_and_next_free_slug()
    test_render_parse_round_trip()
    test_analysis_skill_round_trip()
    test_references_round_trip()
    test_session_signature()
    test_group_digests()
    test_build_session_digests_system_and_user()
    test_extract_local_from_store()
    print("all self-checks passed")

