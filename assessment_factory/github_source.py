"""Pull Nuvepro assessment / guided-project repositories from GitHub.

A logical assessment is a "triplet" of repositories that share a base name and
differ only by suffix: ``_Main`` (learner-facing), ``_Solution`` (reference
answer, optional) and ``_Validation`` (grader, optional). Real repos are
frequently incomplete, so missing members are reported rather than fatal.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


SUFFIXES = ("_Main", "_Solution", "_Validation")
_SUFFIX_RE = re.compile(r"(?i)(.*?)(_(?:Main|Solution|Validation))$")


def load_token(secrets_path: str | None = None) -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if secrets_path and Path(secrets_path).exists():
        for line in Path(secrets_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "GITHUB_TOKEN" and value.strip():
                return value.strip()
    raise RuntimeError("GITHUB_TOKEN not set (env or secrets file)")


def _api(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "assessment-factory",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=40) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def search_repos(org: str, query: str, token: str, *, max_pages: int = 3) -> list[str]:
    names: list[str] = []
    for page in range(1, max_pages + 1):
        q = urllib.parse.quote(f"org:{org} {query}")
        url = f"https://api.github.com/search/repositories?q={q}&per_page=100&page={page}"
        data = _api(url, token)
        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            break
        names.extend(item["name"] for item in items)
        if len(items) < 100:
            break
    return sorted(set(names))


def base_name(repo: str) -> str:
    match = _SUFFIX_RE.match(repo)
    return match.group(1) if match else repo


def group_triplets(repo_names: list[str]) -> dict[str, dict[str, str]]:
    """Group flat repo names into {base: {suffix: full_name}}."""
    groups: dict[str, dict[str, str]] = {}
    for name in repo_names:
        match = _SUFFIX_RE.match(name)
        if not match:
            continue
        base, suffix = match.group(1), match.group(2)
        key = suffix.lstrip("_").lower()
        groups.setdefault(base, {})[key] = name
    return groups


@dataclass
class ClonedTriplet:
    base: str
    org: str
    main_dir: Path | None = None
    solution_dir: Path | None = None
    validation_dir: Path | None = None
    missing: list[str] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return "guided_project" if re.search(r"(?i)(-gp|_gp|guided)", self.base) else "assessment"


def clone_triplet(base: str, org: str, token: str, dest_root: Path) -> ClonedTriplet:
    """Shallow-clone whichever of the three members exist for one base name."""
    triplet = ClonedTriplet(base=base, org=org)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for suffix, attr in (("Main", "main_dir"), ("Solution", "solution_dir"), ("Validation", "validation_dir")):
        repo = f"{base}_{suffix}"
        target = dest_root / base / suffix
        if target.exists():
            setattr(triplet, attr, target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://x-access-token:{token}@github.com/{org}/{repo}.git"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(target)],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and target.exists():
            setattr(triplet, attr, target)
        else:
            triplet.missing.append(suffix)
    return triplet
