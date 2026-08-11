"""Download 20 AWS *_Main assessment repos via GITHUB_TOKEN."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import httpx

from openrouter import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CANDS = ROOT / "data" / "skill_lab" / "aws_main_candidates.json"
OUT_ROOT = ROOT / "data" / "skill_lab" / "assessments_aws_main"
MD_DIR = ROOT / "data" / "skill_lab" / "inputs"


def main() -> None:
    load_dotenv()
    tok = os.environ["GITHUB_TOKEN"].strip()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    cands = json.loads(CANDS.read_text(encoding="utf-8"))
    ap = [
        c
        for c in cands
        if re.search(r"(?i)AP_Main|Assessment", c["name"])
        and not re.search(r"(?i)GP_Main", c["name"])
    ]
    if len(ap) < 20:
        ap = ap + [c for c in cands if c not in ap]
    selected = ap[:20]
    print(f"selected {len(selected)}")
    for s in selected:
        print("-", s["full_name"])

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)
    assessments: list[dict] = []

    with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as client:
        for i, s in enumerate(selected, 1):
            owner, repo = s["full_name"].split("/", 1)
            ref = s.get("default_branch") or "main"
            url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}"
            print(f"[{i}/20] downloading {s['full_name']} ...", flush=True)
            r = client.get(url)
            if r.status_code != 200:
                print(" FAIL", r.status_code, r.text[:120])
                continue
            dest = OUT_ROOT / repo
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                zf.extractall(dest)

            body = ""
            title = repo
            preferred: list[Path] = []
            for p in dest.rglob("*"):
                if not p.is_file():
                    continue
                low = p.name.lower()
                if low in ("assessment-activities.md", "assessment_activities.md", "readme.md"):
                    preferred.append(p)
            pick = next((p for p in preferred if "assessment-activit" in p.name.lower()), None)
            if pick is None and preferred:
                pick = preferred[0]
            if pick is None:
                mds = [p for p in dest.rglob("*.md") if p.is_file()]
                if mds:
                    pick = max(mds, key=lambda p: p.stat().st_size)
            if pick:
                body = pick.read_text(encoding="utf-8", errors="replace")
                for line in body.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

            aid = f"asm_{i:02d}"
            md_path = MD_DIR / f"{aid}.md"
            md_path.write_text(
                f"# {title}\n\nSource: {s['html_url']}\nRepo: {s['full_name']}\n\n{body}\n",
                encoding="utf-8",
            )
            assessments.append(
                {
                    "id": aid,
                    "title": title,
                    "body": body,
                    "source": s["full_name"],
                    "html_url": s["html_url"],
                    "file": str(md_path).replace("\\", "/"),
                }
            )
            print(f"  ok {title[:80]} chars={len(body)}")

    (MD_DIR / "assessments.json").write_text(json.dumps(assessments, indent=2), encoding="utf-8")
    print("DONE", len(assessments))


if __name__ == "__main__":
    main()
