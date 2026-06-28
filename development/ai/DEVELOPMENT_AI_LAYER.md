# Development AI Layer — Architecture

## Purpose

The Development AI Layer standardizes *how* AI models participate in developing SCOS. It exists so that:

1. SCOS development is not single-vendor-dependent at the process level.
2. Model selection for a given task is a deterministic lookup (see [ROUTING_RULES.md](ROUTING_RULES.md)), not a judgment call repeated from scratch every time.
3. Model capability claims are backed by a registry and a rated matrix, not assumption.
4. The layer can absorb new models (commercial or local) without redesigning anything — only the registry and matrix grow.

This layer governs *development-time* activity only: writing, reviewing, testing, and documenting SCOS code. It has no runtime component and ships nothing into `scos/`.

## Responsibilities

- Classify development work into task categories (`TASK_CLASSIFICATION.md`).
- Route each category to a recommended primary model and fallback model (`ROUTING_RULES.md`).
- Maintain a registry of available models with strengths, weaknesses, and recommended use (`MODEL_REGISTRY.md`), backed by a comparable capability rating (`AI_CAPABILITY_MATRIX.md`).
- Define the Claude-unavailable fallback path and how fallback-produced work gets reconciled (`FALLBACK_WORKFLOW.md`).
- Standardize prompt structure across models (`PROMPT_STANDARDS.md`, `prompts/`).
- Define the actual step-by-step loop for each working mode (`workflows/`).
- Define the minimum bar work must clear before being committed (`QUALITY_GUIDELINES.md`).
- Provide a place to record real-world model performance over time (`../benchmarks/`) and score it against a fixed rubric (`../evaluation/`).
- Describe how the layer itself is expected to evolve (`ROADMAP.md`).

## Boundaries

The Development AI Layer **never**:

- Modifies, generates into, or depends on any production directory: `scos/`, `source/`, `memory/`, `assets/`, `analytics/`, `rendering/`, `workflow/`, `tests/`.
- Changes SCOS runtime behavior, dependencies, or configuration.
- Installs or configures editor extensions, Ollama, or any local tooling.
- Implements routing, automation, or model-calling code. Routing in v1 is a document a developer reads, not software that executes.

Everything this layer produces lives under `development/`. If a future phase of the roadmap *does* implement an automatic router, it gets its own explicitly-scoped follow-up — not a silent expansion of this documentation layer's mandate.

## Design principles

- **Local-first.** Fallback capability assumes local models running via Ollama, not a second cloud vendor — the goal is resilience against any single vendor, including a second one.
- **Avoid vendor lock-in at the process level.** Prompts, task classification, and quality bars are written to be model-agnostic; nothing in this layer assumes Claude-specific behavior except where Claude is explicitly named as the routed model.
- **Deterministic over judgment-based.** Given a task category, the model to use is a lookup, not a fresh decision — `ROUTING_RULES.md` exists precisely so this isn't re-litigated per task.
- **Evidence over impression.** Model choice is justified by `MODEL_REGISTRY.md` + `AI_CAPABILITY_MATRIX.md` (and, once populated, `../benchmarks/` + `../evaluation/`), not by which model "feels" better.
- **Extensible by addition, not by rewrite.** Adding a model means adding rows/sections to existing docs, not restructuring them.

## Future extensibility

New models are onboarded by:

1. Adding an entry to `MODEL_REGISTRY.md` (strengths/weaknesses/best use cases/limitations/recommended tasks).
2. Adding a column to `AI_CAPABILITY_MATRIX.md`.
3. Adding a benchmark directory under `../benchmarks/<model>/`.
4. Optionally adjusting `ROUTING_RULES.md` if the new model should become a primary (not just fallback) for some task category.

No other document needs to change shape — this is the mechanism that keeps the layer redesign-free as models change. See [ROADMAP.md](ROADMAP.md) for how onboarding is expected to get more automated over time.
