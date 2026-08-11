"""Automatic comparison metrics: sacrebleu + OpenRouter embedding cosine."""

from __future__ import annotations

import math
from typing import Any

from openrouter import OpenRouterSettings, embeddings
from sacrebleu.metrics import BLEU

from .models import Assessment

# ponytail: clip long labs for embedding token limits; raise if models truncate badly
_EMBED_CHARS = 6000


def _text(a: Assessment) -> str:
    return f"{a.title}\n\n{a.body}".strip()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _by_id(items: list[Assessment]) -> dict[str, Assessment]:
    return {a.id: a for a in items}


def _pairs_from_sme(
    generated: list[Assessment],
    holdout: list[Assessment],
    pairs: list[dict[str, Any]] | None,
) -> list[tuple[Assessment, Assessment]] | None:
    if not pairs:
        return None
    gmap, hmap = _by_id(generated), _by_id(holdout)
    out: list[tuple[Assessment, Assessment]] = []
    for p in pairs:
        gid, hid = p.get("generated_id"), p.get("holdout_id")
        if gid in gmap and hid in hmap:
            out.append((gmap[gid], hmap[hid]))
    return out or None


def _pairs_greedy_embedding(
    generated: list[Assessment],
    holdout: list[Assessment],
    gen_vecs: list[list[float]],
    hold_vecs: list[list[float]],
) -> list[tuple[Assessment, Assessment]]:
    """Greedy 1:1: for each generated, take best unused holdout by cosine."""
    used: set[int] = set()
    out: list[tuple[Assessment, Assessment]] = []
    for i, g in enumerate(generated):
        best_j, best_s = -1, -1.0
        for j, h in enumerate(holdout):
            if j in used:
                continue
            s = _cosine(gen_vecs[i], hold_vecs[j])
            if s > best_s:
                best_s, best_j = s, j
        if best_j < 0:
            break
        used.add(best_j)
        out.append((g, holdout[best_j]))
    return out


def _pairs_index(
    generated: list[Assessment], holdout: list[Assessment]
) -> list[tuple[Assessment, Assessment]]:
    n = min(len(generated), len(holdout))
    return list(zip(generated[:n], holdout[:n], strict=True))


def compute_automatic_metrics(
    generated: list[Assessment],
    holdout: list[Assessment],
    pairs: list[dict[str, Any]] | None = None,
    *,
    settings: OpenRouterSettings | None = None,
) -> dict[str, Any]:
    """BLEU + embedding cosine for gen vs holdout.

    Pairing: SME `pairs` if present; else greedy best-match by embedding cosine;
    else index-aligned gen_i↔holdout_i.
    """
    if not generated or not holdout:
        return {
            "pairing": "empty",
            "bleu": {"corpus": None, "mean_sentence": None, "pairs": []},
            "embedding": {"model": None, "mean_cosine": None, "pairs": []},
        }

    cfg = settings or OpenRouterSettings.from_env()
    gen_texts = [_text(a)[:_EMBED_CHARS] for a in generated]
    hold_texts = [_text(a)[:_EMBED_CHARS] for a in holdout]
    all_vecs, emb_meta = embeddings(gen_texts + hold_texts, settings=cfg)
    gen_vecs = all_vecs[: len(generated)]
    hold_vecs = all_vecs[len(generated) :]

    sme = _pairs_from_sme(generated, holdout, pairs)
    if sme is not None:
        paired = sme
        pairing = "sme_pairs"
    elif gen_vecs and hold_vecs:
        paired = _pairs_greedy_embedding(generated, holdout, gen_vecs, hold_vecs)
        pairing = "greedy_embedding"
    else:
        paired = _pairs_index(generated, holdout)
        pairing = "index"

    gmap = {a.id: i for i, a in enumerate(generated)}
    hmap = {a.id: i for i, a in enumerate(holdout)}

    bleu_metric = BLEU(effective_order=True)
    hyps = [_text(g) for g, _ in paired]
    refs = [[_text(h) for _, h in paired]]
    corpus = bleu_metric.corpus_score(hyps, refs)

    bleu_pairs: list[dict[str, Any]] = []
    emb_pairs: list[dict[str, Any]] = []
    sent_scores: list[float] = []
    cos_scores: list[float] = []

    for g, h in paired:
        sent = bleu_metric.sentence_score(_text(g), [_text(h)])
        cos = _cosine(gen_vecs[gmap[g.id]], hold_vecs[hmap[h.id]])
        sent_scores.append(float(sent.score))
        cos_scores.append(cos)
        bleu_pairs.append(
            {
                "generated_id": g.id,
                "holdout_id": h.id,
                "bleu": round(float(sent.score), 4),
            }
        )
        emb_pairs.append(
            {
                "generated_id": g.id,
                "holdout_id": h.id,
                "cosine": round(cos, 6),
            }
        )

    return {
        "pairing": pairing,
        "bleu": {
            "corpus": round(float(corpus.score), 4),
            "mean_sentence": round(sum(sent_scores) / len(sent_scores), 4) if sent_scores else None,
            "pairs": bleu_pairs,
        },
        "embedding": {
            "model": emb_meta.get("model"),
            "mean_cosine": round(sum(cos_scores) / len(cos_scores), 6) if cos_scores else None,
            "pairs": emb_pairs,
        },
    }
