"""Download assessment markdown from *_Main repos WITHOUT extracting to disk.

Reads each preferred markdown file straight from the in-memory zipball so we
avoid Windows MAX_PATH (260) failures on long workspace paths. Writes only the
short outputs: data/skill_lab/inputs/asm_XX.md and inputs/assessments.json.
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
CANDS = ROOT / "data" / "skill_lab" / "aws_main_candidates.json"
MD_DIR = ROOT / "data" / "skill_lab" / "inputs"

PREFERRED = ("assessment-activities.md", "assessment_activities.md", "readme.md")


def _pick_member(names: list[str]) -> str | None:
    md = [n for n in names if n.lower().endswith(".md")]
    if not md:
        return None
    # 1) assessment-activities.md anywhere
    for n in md:
        if "assessment-activit" in n.lower():
            return n
    # 2) any other preferred basename
    for n in md:
        if Path(n).name.lower() in PREFERRED:
            return n
    # 3) fallback: leave to caller (largest) — return None to signal
    return None


def main() -> None:
    load_dotenv()
    tok = os.environ["GITHUB_TOKEN"].strip()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    cands = json.loads(CANDS.read_text(encoding="utf-8"))
    MD_DIR.mkdir(parents=True, exist_ok=True)
    assessments: list[dict] = []

    with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as client:
        for i, s in enumerate(cands, 1):
            owner, repo = s["full_name"].split("/", 1)
            ref = s.get("default_branch") or "main"
            url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}"
            print(f"[{i}/{len(cands)}] {s['full_name']} ...", flush=True)
            r = client.get(url)
            if r.status_code != 200:
                print("  FAIL", r.status_code, r.text[:120])
                continue

            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                member = _pick_member(names)
                if member is None:
                    md = [n for n in names if n.lower().endswith(".md")]
                    if md:
                        member = max(md, key=lambda n: zf.getinfo(n).file_size)
                body = ""
                if member:
                    body = zf.read(member).decode("utf-8", errors="replace")

            title = repo
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
            print(f"  ok  {title[:70]}  chars={len(body)}  from={member}")

    (MD_DIR / "assessments.json").write_text(
        json.dumps(assessments, indent=2), encoding="utf-8"
    )
    print("DONE", len(assessments), "->", MD_DIR / "assessments.json")


if __name__ == "__main__":
    main()
