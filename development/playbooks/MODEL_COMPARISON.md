# Playbook — Compare Models

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

## Steps

1. Fill out [../templates/EXPERIMENT_TEMPLATE.md](../templates/EXPERIMENT_TEMPLATE.md), stating the hypothesis and success criteria before running anything.
2. Run the identical task on 2 or more models.
3. Record each run via [../templates/BENCHMARK_TEMPLATE.md](../templates/BENCHMARK_TEMPLATE.md) into the matching `development/benchmarks/<model>/README.md`.
4. Score the runs via [../evaluation/SCORING.md](../evaluation/SCORING.md) if a formal comparison is needed (not required for an informal check).
5. If the result changes a rating, update [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md) and note the change in its revision history, citing this comparison.
6. Any resulting change to [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) must go through [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md) — a comparison result alone does not directly edit routing; it's the evidence a change control request points to.

## What not to do

Do not change a routing rule directly from a single comparison run without going through the evidence chain in [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md) — see [../anti-patterns/BAD_ROUTING.md](../anti-patterns/BAD_ROUTING.md).
