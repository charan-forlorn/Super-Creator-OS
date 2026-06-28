# SCOS Development AI Layer

## Why this exists

SCOS development currently runs through a single implementation model: Claude Code. That is a single point of failure for the *process* of building SCOS — not for SCOS itself, which runs without any AI model at all. If Claude Code is unavailable (outage, rate limit, account issue, network), development stops, even though nothing about the production system requires it to.

The Development AI Layer is the documented answer to that risk: a process-level definition of how more than one AI model can participate in developing SCOS, with Claude as the primary model and local models (via Ollama) as a defined fallback and secondary option for well-scoped, lower-risk work.

## Goals

- Define deterministic rules for which model handles which kind of development task.
- Make Claude unavailability survivable: development can continue on local models without inventing a process on the spot.
- Make model evaluation evidence-based — capability claims backed by a registry, a capability matrix, and a scoring rubric, not by impression.
- Keep the layer fully decoupled from the SCOS runtime so it can evolve independently and be extended to future models without redesign.

## Scope

- Documentation, routing rules, prompt templates, and workflow definitions for *developing* SCOS.
- Model selection guidance for categories of engineering work (architecture, implementation, testing, review, debugging, documentation, refactoring, planning, research).
- A structure for recording and scoring model performance over time (`development/benchmarks/`, `development/evaluation/`).

## Non-goals

- No production code, runtime behavior, configuration, or dependency in SCOS is touched by this layer or by adopting it.
- No router, automation, or API is implemented in v1 — routing is a human-followed decision table, not software (see [ROADMAP.md](ROADMAP.md)).
- No editor/extension configuration (VS Code, Continue, Ollama setup) is included here — this layer documents *process*, not tool installation.

## High-level workflow

```text
  New development task
          |
          v
  TASK_CLASSIFICATION.md  --> what kind of task is this?
          |
          v
  ROUTING_RULES.md        --> which model should handle it?
          |
          v
  MODEL_REGISTRY.md /
  AI_CAPABILITY_MATRIX.md --> confirm the model fits (strengths/limits, rated capability)
          |
          v
  prompts/<category>.md   --> structured prompt template (PROMPT_STANDARDS.md compliant)
          |
          v
  workflows/<model>.md    --> the step-by-step dev loop for that model
          |
          v
  QUALITY_GUIDELINES.md   --> acceptance checklist before commit
          |
          v
  development/evaluation/ --> (optional) score the output against SCORING.md
  development/benchmarks/ --> (optional) log latency/quality/cost for this run
          |
          v
       Commit
```

If Claude is unavailable mid-task, [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md) defines the handoff and recovery path instead of improvising one.

## Where to go next

- New to the layer: read [DEVELOPMENT_AI_LAYER.md](DEVELOPMENT_AI_LAYER.md) for the full architecture.
- Deciding which model to use for a task: [ROUTING_RULES.md](ROUTING_RULES.md) + [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md) + [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md).
- Claude is down right now: [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md).
- Writing a prompt: [PROMPT_STANDARDS.md](PROMPT_STANDARDS.md) and the [prompts/](prompts/) directory.
- Running or reviewing a model-driven dev session: [workflows/](workflows/).
- Recording how well a model actually performed: [../benchmarks/README.md](../benchmarks/README.md) and [../evaluation/README.md](../evaluation/README.md).
