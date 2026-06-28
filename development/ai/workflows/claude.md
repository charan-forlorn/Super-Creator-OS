# Workflow — Claude-only Development

The standard dev loop when Claude Code is the acting model (the default case — see [ROUTING_RULES.md](../ROUTING_RULES.md)).

## Loop

1. Classify the task per [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md).
2. Confirm Claude is the routed model for this category (it usually is — Claude is primary for everything except Testing/Documentation/Refactoring/Research, per [ROUTING_RULES.md](../ROUTING_RULES.md)).
3. Use the matching template from [prompts/](.) (the parent `prompts/` directory) filled in for the specific task.
4. Implement / produce output.
5. Self-check against [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md)'s validation checklist.
6. Commit (no special tag needed — Claude-authored work is the default, untagged case; only fallback work gets a `[fallback:*]` tag per [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md)).

## Git workflow

- Standard commit boundaries: one logical change per commit, matching the rest of the project's existing commit conventions.
- No special review step is required beyond the self-check in step 5 — Claude is the highest-rated model in [AI_CAPABILITY_MATRIX.md](../AI_CAPABILITY_MATRIX.md) for most categories, so this is the layer's baseline trust level.
- Exception: if the task was a second-opinion review of another model's work (rule 5 in [ROUTING_RULES.md](../ROUTING_RULES.md)), the review's verdict is recorded in the commit message or PR description, not silently applied.
