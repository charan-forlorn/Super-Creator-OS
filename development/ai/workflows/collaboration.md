# Workflow — Multi-model Collaboration

How Claude and a local model work together intentionally on the same piece of work — distinct from fallback (where a local model substitutes for an unavailable Claude). See [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md) for the substitution case.

## Pattern: design → implement boilerplate → review

1. **Claude designs.** Architecture-category work per [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md), using [prompts/architecture.md](../prompts/architecture.md). Output names the files/interfaces to be built.
2. **Ollama implements mechanical pieces.** Anything in the design that's pattern-following (boilerplate tests, repetitive scaffolding, documentation of the new structure) is split out and routed to Ollama per [ROUTING_RULES.md](../ROUTING_RULES.md), using [prompts/testing.md](../prompts/testing.md) / [prompts/documentation.md](../prompts/documentation.md) as appropriate.
3. **Claude reviews.** The combined result is reviewed by Claude using [prompts/review.md](../prompts/review.md) before commit — this is the standing application of [ROUTING_RULES.md](../ROUTING_RULES.md) rule 5 (reviewer differs from author) for this collaboration pattern specifically.

## Pattern: adversarial second opinion

For any task where being wrong is costly (production implementation, debugging a subtle defect), get a second opinion from a different model than the one that produced the work, per [ROUTING_RULES.md](../ROUTING_RULES.md) rule 5 and [prompts/review.md](../prompts/review.md). Disagreements between the two are resolved by Claude, since Claude is the highest-rated model for judgment-heavy categories in [AI_CAPABILITY_MATRIX.md](../AI_CAPABILITY_MATRIX.md).

## Git workflow

- Each model's contribution lands as its own commit (design commit, implementation commit, review-fix commit) rather than being squashed into one — this keeps the [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md)-style `[fallback:*]` tagging convention meaningful and keeps authorship traceable per model.
- The final commit in a collaboration sequence is the one that must pass [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md)'s validation checklist in full, even if intermediate commits (e.g. a first-pass boilerplate commit) wouldn't have on their own.
