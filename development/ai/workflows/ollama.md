# Workflow — Ollama-only Development

The dev loop when a local model (Qwen2.5-Coder or DeepSeek-Coder, via Ollama) is the acting model — either because it's the routed primary for this task category, or because of fallback (see [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md)).

## Loop

1. Classify the task per [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md).
2. Confirm the local model is appropriate: either it's the routed primary (Testing, Documentation, Refactoring, Research per [ROUTING_RULES.md](../ROUTING_RULES.md)), or this is an explicit fallback because Claude is unavailable.
3. Use the matching template from [prompts/](.) (the parent `prompts/` directory) filled in for the specific task.
4. Implement / produce output locally.
5. Self-check against [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md)'s validation checklist — same bar as Claude, not a relaxed one.
6. Commit. If this was a fallback (not a routed-primary task), tag the commit `[fallback:<model>]` per [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md); routed-primary local work needs no special tag.
7. Mid-task escalation check: if the task is revealed to touch a production directory or require architecture-level reasoning, stop per [ROUTING_RULES.md](../ROUTING_RULES.md)'s escalation rule and hand off to [claude.md](claude.md) instead of finishing it locally.

## Git workflow

- Same commit-boundary conventions as Claude-authored work.
- Fallback-tagged commits are queued for a Claude review pass at the next recovery point — see [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md)'s recovery procedure. Routed-primary local work (e.g. a unit test commit) does not require this queued review, since it was the intended model for that category, not a substitute for an unavailable one.
