# Prompt Standards

Universal rules for writing prompts in this layer (templates in [prompts/](prompts/)), so output quality doesn't depend on which model receives the prompt.

## Prompts must be:

- **Deterministic.** The same prompt against the same inputs should produce comparably-scoped output every time. Avoid open-ended phrasing ("improve this however you see fit") in favor of a stated scope and explicit constraints.
- **Reusable.** A prompt template is parameterized (task description, file paths, constraints) rather than rewritten per task. Templates in [prompts/](prompts/) are meant to be filled in, not replaced.
- **Vendor-agnostic.** No prompt should rely on a model-specific quirk (a particular system-prompt convention, a particular tool-call format) to produce correct output. If a model needs different framing to follow the same instruction, that's a [MODEL_REGISTRY.md](MODEL_REGISTRY.md) limitation to document, not a reason to fork the prompt.
- **Minimal token usage.** State the task, the constraints, and the acceptance bar. Skip preamble, flattery, and restating context the model can read from the files it's given.
- **Structured.** Every prompt has the same shape (below), so a developer reading a prompt template six months from now can tell at a glance what it does and doesn't cover.

## Required structure

Every prompt template under [prompts/](prompts/) follows this shape:

1. **Task** — one sentence, what is being asked.
2. **Scope** — exact files/directories in play. If production directories are in scope, name them explicitly (and confirm against [ROUTING_RULES.md](ROUTING_RULES.md) that this task category is routed to a model allowed to touch them).
3. **Constraints** — hard limits (no new dependencies, no API changes, must stay deterministic, etc.) carried over from the relevant section of [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md).
4. **Acceptance bar** — what "done" looks like (tests pass, no regression, doc reads as complete, etc.).
5. **Output format** — what the model should return (a diff, a new file, a written explanation) so output is consumable without back-and-forth clarification.

## Anti-patterns to avoid

- Prompts that assume the model remembers prior conversation context it wasn't given in this prompt.
- Prompts that ask for "best practices" without naming which ones — name the constraint instead.
- Prompts that mix multiple task categories (e.g. "refactor this and also write the architecture doc for it") — split per [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md) so each piece routes to the right model.
- Prompts that omit the acceptance bar — without it, "done" is whatever the model decides, which defeats the determinism goal above.
