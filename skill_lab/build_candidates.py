"""Build data/skill_lab/aws_main_candidates.json from a fixed repo list.

Resolves each repo's default_branch + html_url via the GitHub API using
GITHUB_TOKEN so download_aws_main.py can zipball the correct ref.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from openrouter import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "skill_lab" / "aws_main_candidates.json"

OWNER = "Nuvepro-Technologies-Pvt-Ltd"
REPOS = [
    "Infosys-AWS-Developer-Associate-Trail-Assessment-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment1_Pool3-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment3.3-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment3.2-AP_Main",
    "Infosys-AWS-Developer-Associate-Pool3-Assessment3.2-AP_MAIN",
    "Infosys-AWS-Developer-Associate-Pool2-Assessment2.2-AP_MAIN",
    "Infosys-AWS-Cloud-Developer-Associate-Pool3-RealTimeEnergyGrid_MAIN",
    "Infosys-AWS-Developer-Associate-Assessment2.3-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment2.2-AP_Main",
    "AWS-Cloud-Developer-Associate-Pool2-RealTimeLogisticsShipmentTracker_MAIN",
    "Infosys-AWS-Developer-Associate-Assessment1_Pool2-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment1-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment3-AP_Main",
    "Infosys-AWS-Developer-Associate-Assessment2-AP_Main",
    "Trainocate-AWS-CloudOps-Module4-Monitoring-Alerting-Operational-Visibility-at-Scale_Main",
    "Trainocate-AWS-Track3-Automation-Tool-Test_MAIN",
    "Sample-Validation-AWS_02_Main",
    "Sample-Validation-AWS_Main",
    "AWS-Bedrock-CustomerBusinessAssistantBot-AP_Main",
]


def main() -> None:
    load_dotenv()
    tok = os.environ["GITHUB_TOKEN"].strip()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cands: list[dict] = []
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        for repo in REPOS:
            full = f"{OWNER}/{repo}"
            r = client.get(f"https://api.github.com/repos/{full}")
            if r.status_code != 200:
                print(f"WARN {full} -> HTTP {r.status_code} {r.text[:100]}")
                cands.append(
                    {
                        "name": repo,
                        "full_name": full,
                        "default_branch": "main",
                        "html_url": f"https://github.com/{full}",
                    }
                )
                continue
            data = r.json()
            cands.append(
                {
                    "name": repo,
                    "full_name": data.get("full_name", full),
                    "default_branch": data.get("default_branch", "main"),
                    "html_url": data.get("html_url", f"https://github.com/{full}"),
                }
            )
            print(f"ok  {full}  branch={data.get('default_branch')}")

    OUT.write_text(json.dumps(cands, indent=2), encoding="utf-8")
    print(f"WROTE {OUT} ({len(cands)} repos)")


if __name__ == "__main__":
    main()
