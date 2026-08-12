"""Merge usable existing assessments + newly downloaded repos into exactly 20.

- Keeps existing inputs/assessments.json entries that have non-empty bodies.
- Downloads NEW_REPOS markdown in-memory (skips code-only repos).
- Fills up to TARGET=20, re-ids asm_01..asm_20, rewrites assessments.json + md.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import httpx

from openrouter import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MD_DIR = ROOT / "data" / "skill_lab" / "inputs"
JSON_PATH = MD_DIR / "assessments.json"
TARGET = 20
MIN_CHARS = 500  # reject README stubs / near-empty bodies

OWNER = "Nuvepro-Technologies-Pvt-Ltd"
NEW_REPOS = [
    "Skillsoft_AWS_S3_File_encryption_project_Main",
    "Skillsoft_AWS_s3_versioned_bucket_Main",
    "Skillsoft_AWS_Secure_s3_access_Main",
    "Skillsoft_AWS_Implement_IAM_policy_Main",
    "Skillsoft_AWS_create_IAM_user_Main",
    "Skillsoft_AWS_S3_Multiregion_bucket_Main",
    "Testing-PostgreSQL-to-MySQL-using-AWS-DMS-AP_Main",
    "AWS-BedRock-Customer-Business-AssistantBot-AP_Main",
    "Trainocate-AWS-PersonalizedRecommendationsApplicationWithBedrockInEC2_Main",
    "Microland-AWS-App-Create-ec2-autoscaling-AP_Main",
]

PREFERRED = ("assessment-activities.md", "assessment_activities.md",
             "guidedproject-activities.md", "challenge-activities.md", "readme.md")


def _pick_member(names: list[str]) -> str | None:
    md = [n for n in names if n.lower().endswith(".md")]
    if not md:
        return None
    for kw in ("assessment-activit", "assessment_activit", "guidedproject-activit",
               "challenge-activit"):
        for n in md:
            if kw in n.lower():
                return n
    for n in md:
        if Path(n).name.lower() in PREFERRED:
            return n
    return max(md, key=lambda n: len(n))  # any md; caller re-checks size


def _download_md(client: httpx.Client, full: str) -> tuple[str, str | None]:
    r = client.get(f"https://api.github.com/repos/{full}/zipball/main")
    if r.status_code != 200:
        return "", None
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        member = _pick_member(names)
        if member is None:
            return "", None
        body = zf.read(member).decode("utf-8", errors="replace")
    return body, member


def main() -> None:
    load_dotenv()
    tok = os.environ["GITHUB_TOKEN"].strip()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    existing = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    usable = [a for a in existing if len((a.get("body") or "").strip()) >= MIN_CHARS]
    print(f"usable existing: {len(usable)}")
    have_sources = {a.get("source") for a in usable}

    with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as client:
        for repo in NEW_REPOS:
            if len(usable) >= TARGET:
                break
            full = f"{OWNER}/{repo}"
            if full in have_sources:
                print(f"skip dup {full}")
                continue
            body, member = _download_md(client, full)
            if len(body.strip()) < MIN_CHARS:
                print(f"  SKIP stub/code-only ({len(body.strip())} chars): {full}")
                continue
            title = repo
            for line in body.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            usable.append({
                "title": title,
                "body": body,
                "source": full,
                "html_url": f"https://github.com/{full}",
            })
            print(f"  add {full}  chars={len(body)}  from={member}")

    if len(usable) < TARGET:
        print(f"WARNING: only {len(usable)} usable, need {TARGET}")
    final = usable[:TARGET]

    # Re-id and rewrite outputs
    for old in MD_DIR.glob("asm_*.md"):
        old.unlink()
    out: list[dict] = []
    for i, a in enumerate(final, 1):
        aid = f"asm_{i:02d}"
        md_path = MD_DIR / f"{aid}.md"
        md_path.write_text(
            f"# {a['title']}\n\nSource: {a['html_url']}\nRepo: {a['source']}\n\n{a['body']}\n",
            encoding="utf-8",
        )
        out.append({
            "id": aid,
            "title": a["title"],
            "body": a["body"],
            "source": a["source"],
            "html_url": a["html_url"],
            "file": str(md_path).replace("\\", "/"),
        })
    JSON_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"DONE {len(out)} -> {JSON_PATH}")


if __name__ == "__main__":
    main()
