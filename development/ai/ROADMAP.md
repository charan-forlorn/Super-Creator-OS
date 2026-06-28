# Roadmap

Future evolution of the Development AI Layer. This is a roadmap only — nothing beyond **Phase 1: Development AI Layer v1** (this current set of documents) is implemented.

## Phase 1 — Development AI Layer v1 (current)

Documentation-only foundation: model registry, capability matrix, routing rules, task classification, prompt standards, quality guidelines, fallback workflow, and empty benchmark/evaluation scaffolding. No automation, no production code touched.

## Phase 2 — Prompt Library

Expand [prompts/](prompts/) from one template per category into a fuller library: variants per model where genuinely needed, and a versioning convention so prompt changes can be tracked against the outcomes they produced (linking forward to Phase 5's benchmarking).

## Phase 3 — Model Routing (still manual)

Refine [ROUTING_RULES.md](ROUTING_RULES.md)'s decision rules based on real fallback usage recorded via [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md) — still a document a developer reads, not software.

## Phase 4 — Automatic Router

A tool (not yet specified) that reads [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md) and [ROUTING_RULES.md](ROUTING_RULES.md) and suggests a model for a given task description. This phase is the first to touch tooling rather than pure documentation, and will get its own scoped plan when it's taken up — it is not authorized by this roadmap entry alone.

## Phase 5 — Performance Benchmark

Populate `../benchmarks/<model>/` with real run data (Task, Latency, Quality, Pass, Fail, Token, Cost) instead of the empty schema scaffolding shipped in v1.

## Phase 6 — Model Evaluation

Apply `../evaluation/SCORING.md`'s rubric to real benchmark data from Phase 5, replacing the illustrative example scores with measured ones, and feed corrected ratings back into [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md).

## Phase 7 — Dynamic Routing

Use accumulated benchmark + evaluation data to adjust routing automatically per task category, rather than the static table in [ROUTING_RULES.md](ROUTING_RULES.md) v1.

## Phase 8 — Self-learning Routing

Routing that updates its own model preferences over time from outcome data, without manual table edits. The furthest-out phase; depends entirely on Phases 5–7 producing enough real evidence to learn from.

No phase beyond Phase 1 is implemented by this document. Each phase, when taken up, gets its own explicit plan and scope — this roadmap states direction, not authorization.
