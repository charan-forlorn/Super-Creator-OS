# Quality Guidelines

Minimum standards work must clear before being committed, regardless of which model produced it. The bar does not change between Claude and a fallback model — see [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md).

## Code quality

- No production directory (`scos/`, `source/`, `memory/`, `assets/`, `analytics/`, `rendering/`, `workflow/`, `tests/`) is changed without the change being in-scope for the originating task.
- No new dependency, runtime behavior change, or configuration change is introduced silently — these must be a named, explicit part of the task, not a side effect.
- Existing patterns and utilities are reused; no parallel implementation of something that already exists.

## Documentation quality

- Every document is complete on its own — no stub sections, no "TODO: fill in later" left in committed docs.
- Cross-references to other docs in this layer are accurate (the linked file and section actually exist and say what's implied).
- Examples and illustrative data are explicitly labeled as such (see [evaluation/SCORING.md](../evaluation/SCORING.md) for the convention) — never presented as if they were real measurements.

## Prompt quality

- Every prompt used follows [PROMPT_STANDARDS.md](PROMPT_STANDARDS.md)'s required structure (Task / Scope / Constraints / Acceptance bar / Output format).
- A prompt that had to be revised more than once for the same task is a signal to fix the template in [prompts/](prompts/), not just the one-off instance.

## Review process

1. Self-check against this checklist before considering work done.
2. For anything routed to a fallback model, a Claude review pass happens at the next recovery point (see [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md)) even if it already passed self-check.
3. For anything flagged under [ROUTING_RULES.md](ROUTING_RULES.md) rule 5 (second-opinion review), the reviewing model must be different from the authoring model.

## Validation checklist

- [ ] Task classified correctly per [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md)
- [ ] Model used matches [ROUTING_RULES.md](ROUTING_RULES.md) for that classification
- [ ] No production directory touched unless the task was explicitly routed as production-relevant
- [ ] No dependency/config/runtime change introduced outside task scope
- [ ] Documentation (if any) is complete, not a stub
- [ ] Fallback-authored work is tagged and queued for review per [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md)

## Acceptance criteria

Work is acceptable to commit when every item in the validation checklist is satisfied. Work that fails any item is not committed until corrected — escalating to Claude per [ROUTING_RULES.md](ROUTING_RULES.md) if the failure reason is a capability gap in the model that produced it.
