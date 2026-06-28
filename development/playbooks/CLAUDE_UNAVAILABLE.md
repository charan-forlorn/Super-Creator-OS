# Playbook — Claude Unavailable

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

Operational walk-through of [../ai/FALLBACK_WORKFLOW.md](../ai/FALLBACK_WORKFLOW.md) — read that file for the full decision flow and recovery procedure; this is the condensed step list for use in the moment.

## Steps

1. Confirm Claude is genuinely unavailable for this task (outage, rate limit, auth issue, no network path) — this is a per-task decision, not a mode switch for the whole project.
2. Route to the fallback model named in [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) for this task's category.
3. Confirm the routing using [../checklists/MODEL_SELECTION.md](../checklists/MODEL_SELECTION.md).
4. Work via [../ai/workflows/ollama.md](../ai/workflows/ollama.md).
5. If mid-task you discover this touches a production directory or needs architecture-level reasoning, stop and queue it for Claude instead of finishing it locally.
6. Commit, tagging the commit `[fallback:<model>]`.
7. Once Claude returns: follow the recovery procedure in [../ai/FALLBACK_WORKFLOW.md](../ai/FALLBACK_WORKFLOW.md) — review all `[fallback:*]` commits since the last recovery pass.
