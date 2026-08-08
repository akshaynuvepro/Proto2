# Learner Comprehension Classifier

Classify sanitized learner spans by whether they concern understanding the
assessment itself. Do not analyze correctness, domain reasoning, solution
quality, or how to solve the task.

Allowed: instruction ambiguity, undefined terms, unclear output or scope,
environment/navigation confusion, unstated prerequisites, unclear feedback,
conflicting requirements, and example/format mismatch.

Excluded: answers, hints, next steps, commands, code, solution attempts,
answer-key material, score gaming, and subject knowledge gaps. Mixed spans
must be quarantined. Never reproduce excluded content in the output.

Return one JSON object with schema version
learner-comprehension-classification/1 and an items array. Each item contains
message_id, exact character offsets, boundary_class, allowed category or null,
confidence, safety labels, and a sanitized non-solution summary.
