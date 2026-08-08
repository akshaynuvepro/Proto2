"""Assessment Factory.

End-to-end pipeline that turns real Nuvepro AWS assessment/guided-project
repositories into:

1. a canonical, structured AssessmentRecord (normalization of messy repos),
2. a reviewable/approvable Template (the house-style blueprint),
3. a reviewable/approvable Skill file (SKILL.md an LLM uses to author new work),
4. a newly generated assessment produced from an approved skill + a brief,
   verified by deterministic consistency checks.

The deterministic stages (pull, normalize, template, skill compile,
consistency) run without any model credentials. Only `generate` requires an
OpenRouter key.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
