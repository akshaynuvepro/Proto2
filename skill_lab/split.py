from __future__ import annotations

import random

from .models import Assessment, Split


def split_train_holdout(
    assessments: list[Assessment],
    *,
    seed: int | None = None,
    train_n: int = 10,
) -> Split:
    if len(assessments) != 20:
        raise ValueError(f"Expected 20 assessments, got {len(assessments)}")
    use_seed = seed if seed is not None else random.randrange(1, 10_000_000)
    rng = random.Random(use_seed)
    shuffled = list(assessments)
    rng.shuffle(shuffled)
    return Split(train=shuffled[:train_n], holdout=shuffled[train_n:], seed=use_seed)
