"""Command-line surface for the assessment factory.

Flow:
    pull          -> clone + normalize repos into canonical records
    build-template-> distill a reviewable Template from records
    review-template
    build-skill   -> compile a structured SKILL.md from an approved template
    review-skill
    ui            -> browse templates and skill files

Only deterministic stages exist; no model credentials are required.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

from . import github_source as ghs
from .llm import ModelSettings, load_env_file
from .schema import utc_now
from .skill import compile_skill, compile_skill_with_model
from .store import FactoryStore
from .template import build_template
from .normalize import normalize_triplet


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "assessment-factory"
DEFAULT_SECRETS = Path(tempfile.gettempdir()) / "opencode" / "secrets.env"


def _repo_to_base(token: str) -> str:
    token = token.strip()
    if not token:
        return ""
    m = re.search(r"github\.com[:/][^/]+/([^/\s]+?)(?:\.git)?$", token)
    if m:
        token = m.group(1)
    return ghs.base_name(token)


def _load_org(args) -> str:
    if args.org:
        return args.org
    import os
    org = os.getenv("GITHUB_ORG", "").strip()
    if org:
        return org
    if Path(args.secrets).exists():
        for line in Path(args.secrets).read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GITHUB_ORG="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("GITHUB_ORG not provided (--org, env, or secrets file)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="assessment-factory", description="AWS assessment template + skill factory")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA, help="artifact store root")
    p.add_argument("--secrets", type=Path, default=DEFAULT_SECRETS, help="secrets.env with GITHUB_TOKEN/ORG")
    p.add_argument("--org", default="", help="GitHub org (overrides env/secrets)")
    sub = p.add_subparsers(dest="command", required=True)

    lr = sub.add_parser("list-repos", help="Search the org for repos")
    lr.add_argument("--query", required=True)

    pull = sub.add_parser("pull", help="Clone + normalize repos into records")
    pull.add_argument("--names", nargs="*", default=[], help="repo names/URLs (any suffix) or base names")
    pull.add_argument("--names-file", type=Path, help="file with one repo name/URL per line")
    pull.add_argument("--search", help="pull all repos matching this org search query")
    pull.add_argument("--limit", type=int, default=0, help="max bases to pull (0 = no limit)")

    sub.add_parser("records", help="List normalized records")

    bt = sub.add_parser("build-template", help="Distill a template from records")
    bt.add_argument("--name", required=True)
    bt.add_argument("--records", nargs="*", default=[], help="record ids (default: all)")
    bt.add_argument("--content-type", default="assessment", choices=["assessment", "guided_project"])

    bs = sub.add_parser("build-skill", help="Generate a structured multi-file skill package from a template")
    bs.add_argument("--template", required=True)
    bs.add_argument("--deterministic", action="store_true", help="Skip the model; use the offline compiler")
    bs.add_argument("--model", default="", help="Override ASSESSMENT_FACTORY_MODEL for this run")

    sub.add_parser("list", help="Summarize records, templates, and skills")

    ui = sub.add_parser("ui", help="Serve the browse UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8799)

    return p


def _pull(args, store: FactoryStore) -> None:
    org = _load_org(args)
    token = ghs.load_token(str(args.secrets))
    names: list[str] = list(args.names)
    if args.names_file and Path(args.names_file).exists():
        names += [ln for ln in Path(args.names_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    bases: list[str] = []
    if args.search:
        found = ghs.search_repos(org, args.search, token)
        bases = sorted(ghs.group_triplets(found).keys())
    for raw in names:
        base = _repo_to_base(raw)
        if base and base not in bases:
            bases.append(base)
    if args.limit:
        bases = bases[: args.limit]
    if not bases:
        raise SystemExit("no repositories resolved to pull (use --names/--names-file/--search)")

    with tempfile.TemporaryDirectory(prefix="af_clone_") as tmp:
        dest = Path(tmp)
        results = []
        for base in bases:
            triplet = ghs.clone_triplet(base, org, token, dest)
            record = normalize_triplet(triplet)
            store.put_record(record)
            results.append(record)
            print(json.dumps({
                "record_id": record.record_id,
                "base_repo": record.base_repo,
                "content_type": record.content_type,
                "grader_format": record.grader_format,
                "testcases": len(record.testcases),
                "total_marks": record.total_marks,
                "has_solution": record.has_solution,
                "has_validation": record.has_validation,
                "warnings": record.warnings,
            }, ensure_ascii=False))
    print(f"\nnormalized {len(results)} record(s) into {store.root / 'records'}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    store = FactoryStore(args.data.resolve())

    if args.command == "list-repos":
        org = _load_org(args)
        token = ghs.load_token(str(args.secrets))
        names = ghs.search_repos(org, args.query, token)
        triplets = ghs.group_triplets(names)
        print(json.dumps({"count_repos": len(names), "count_bases": len(triplets),
                          "bases": sorted(triplets.keys())}, ensure_ascii=False, indent=2))
        return

    if args.command == "pull":
        _pull(args, store)
        return

    if args.command == "records":
        for r in store.list_records():
            print(f"{r.record_id}  [{r.content_type}] {r.base_repo}  "
                  f"tc={len(r.testcases)} marks={r.total_marks} grader={r.grader_format} "
                  f"warn={len(r.warnings)}")
        return

    if args.command == "build-template":
        all_records = store.list_records()
        chosen = (
            [r for r in all_records if r.record_id in set(args.records)]
            if args.records else
            [r for r in all_records if r.content_type == args.content_type]
        )
        if not chosen:
            raise SystemExit("no matching records; run `pull` first")
        template = build_template(chosen, name=args.name, content_type=args.content_type)
        store.put_template(template)
        print(json.dumps({"template_id": template.template_id, "status": template.status,
                          "derived_from": len(template.derived_from)}, ensure_ascii=False, indent=2))
        return

    if args.command == "build-skill":
        template = store.get_template(args.template)
        example = None
        rec_id = (template.canonical_example or {}).get("record_id")
        if rec_id:
            try:
                example = store.get_record(rec_id)
            except FileNotFoundError:
                example = None
        mode = "deterministic"
        if not args.deterministic:
            load_env_file(args.secrets)
            if args.model:
                import os
                os.environ["ASSESSMENT_FACTORY_MODEL"] = args.model
            try:
                settings = ModelSettings.from_env()
                skill = compile_skill_with_model(template, example=example, settings=settings)
                mode = f"model:{settings.model}"
            except RuntimeError as exc:
                print(json.dumps({"warning": f"model unavailable ({exc}); using deterministic compiler"}))
                skill = compile_skill(template)
        else:
            skill = compile_skill(template)
        store.put_skill(skill)
        print(json.dumps({"skill_id": skill.skill_id, "status": skill.status, "generated_by": mode,
                          "files": sorted(skill.files.keys()),
                          "package_dir": str(store.root / 'skills' / skill.skill_id)},
                         ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        print(json.dumps({
            "records": [{"id": r.record_id, "base": r.base_repo, "type": r.content_type,
                         "marks": r.total_marks, "grader": r.grader_format} for r in store.list_records()],
            "templates": [{"id": t.template_id, "name": t.name, "status": t.status,
                           "derived_from": len(t.derived_from)} for t in store.list_templates()],
            "skills": [{"id": s.skill_id, "name": s.name, "status": s.status,
                        "template": s.template_id} for s in store.list_skills()],
        }, ensure_ascii=False, indent=2))
        return

    if args.command == "ui":
        from .ui import serve
        serve(store, host=args.host, port=args.port)
        return

    raise AssertionError(args.command)


if __name__ == "__main__":
    main()
