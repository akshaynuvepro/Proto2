# 🧪 Assessment Skill Lab

A **closed-loop skill optimizer** for assessment authoring.

## What it does

1. You provide **20 approved SME assessments**
2. It splits them **10 train / 10 holdout**
3. Learns an authoring **skill** from the train set
4. **Generates** 10 new assessments with that skill
5. An SME comparator agent **scores** them against the holdout (baseline)
6. An improver agent produces an **improved skill**
7. It **re-generates and re-scores** with the improved skill
8. You get a **Δ verdict**: did the skill measurably improve?

## Iterating

Each run improves the skill by one generation (v1 → v2 → v3 …).
Use `resume <run_id>` to continue optimizing across runs until the
score plateaus (delta stays inside the ±0.3 judge-noise band).

## Notes

- SME rubric score (structure / house-style / depth / clarity / completeness)
  is the quality grade. BLEU and embedding cosine are shown only as
  **topic-drift indicators** — they do not measure quality.
- All artifacts are saved under `data/skill_lab/runs/<run_id>/`.
