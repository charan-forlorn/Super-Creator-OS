# Playbook — Start a New Feature

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

## Steps

1. Classify the work per [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md).
2. Route to a model per [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md), confirming with [../checklists/MODEL_SELECTION.md](../checklists/MODEL_SELECTION.md).
3. Fill out [../templates/TASK_TEMPLATE.md](../templates/TASK_TEMPLATE.md) for the feature.
4. Run [../checklists/PRE_IMPLEMENTATION.md](../checklists/PRE_IMPLEMENTATION.md).
5. Implement via the matching loop in [../ai/workflows/](../ai/workflows/) (`claude.md` or `ollama.md` depending on the routed model).
6. Run [../checklists/PRE_COMMIT.md](../checklists/PRE_COMMIT.md).
7. Run [../checklists/PRE_PR.md](../checklists/PRE_PR.md) before opening a PR.

## See also

- A worked example of this exact flow: [../examples/feature-example.md](../examples/feature-example.md)
- If Claude is unavailable partway through: switch to [CLAUDE_UNAVAILABLE.md](CLAUDE_UNAVAILABLE.md) and resume from step 5.
