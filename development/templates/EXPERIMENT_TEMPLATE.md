# Template — Experiment

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

For trying a model or approach change before committing to it — e.g. comparing two models on the same task (see [../playbooks/MODEL_COMPARISON.md](../playbooks/MODEL_COMPARISON.md)).

---

**Hypothesis:** `<what you expect to be true, and why — e.g. "DeepSeek-Coder produces comparable documentation quality to Claude at lower cost for module-level docs">`

**What's being compared:** `<models / approaches / prompt variants in scope>`

**Task used for comparison:** `<exact task, scoped per ../templates/TASK_TEMPLATE.md>`

**Success criteria:** `<what result would confirm or refute the hypothesis — state this before running, not after>`

**Recording:** each run logged via [BENCHMARK_TEMPLATE.md](BENCHMARK_TEMPLATE.md) into the matching `development/benchmarks/<model>/README.md`.

**Scoring (if applicable):** [../evaluation/SCORING.md](../evaluation/SCORING.md) — only if a formal score will be produced; not required for a quick informal comparison.

**Outcome:** `<filled in after the experiment — confirmed / refuted / inconclusive, and what changed as a result (e.g. an update to ../ai/AI_CAPABILITY_MATRIX.md)>`
