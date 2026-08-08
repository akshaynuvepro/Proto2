"""Pinned SkillOpt 0.2 CLI compatibility launcher.

SkillOpt 0.2 keeps its environment registry in its CLI module and does not
publish an external entry-point hook. This launcher registers the adapter in
that registry, then delegates to the unmodified trainer.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from scripts import train as skillopt_train
    except ImportError as exc:
        raise SystemExit("SkillOpt 0.2.0 is not installed") from exc
    from .adapter import AssessmentImproverAdapter

    registry = getattr(skillopt_train, "_ENV_REGISTRY", None)
    if not isinstance(registry, dict):
        raise SystemExit(
            "Installed SkillOpt is incompatible: expected the 0.2 environment registry"
        )
    registry["assessment_improver"] = AssessmentImproverAdapter
    skillopt_train.main()


if __name__ == "__main__":
    main()
