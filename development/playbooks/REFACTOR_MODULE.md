# Playbook — Refactor a Module

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

## Steps

1. Fill out [../templates/CHANGE_REQUEST_TEMPLATE.md](../templates/CHANGE_REQUEST_TEMPLATE.md).
2. Confirm whether the refactor touches a production directory or changes observable behavior — if so, this escalates to Claude per [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md)'s escalation rule, regardless of how the task started.
3. Use [../ai/prompts/refactor.md](../ai/prompts/refactor.md) to scope and execute the refactor via the matching loop in [../ai/workflows/](../ai/workflows/).
4. Confirm behavior is unchanged: existing tests for the affected area pass unmodified.
5. Run [../checklists/PRE_COMMIT.md](../checklists/PRE_COMMIT.md).

## See also

[../anti-patterns/BAD_ROUTING.md](../anti-patterns/BAD_ROUTING.md) for the specific failure mode of treating a refactor as "simple" and skipping the production-directory check in step 2.
