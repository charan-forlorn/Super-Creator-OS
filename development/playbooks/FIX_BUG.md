# Playbook — Fix a Bug

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

## Steps

1. Fill out [../templates/BUG_REPORT_TEMPLATE.md](../templates/BUG_REPORT_TEMPLATE.md).
2. Root-cause the bug using the model routed for Debugging in [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) — Claude for production-touching bugs, per the production-touch rule.
3. Implement the fix via the matching loop in [../ai/workflows/](../ai/workflows/).
4. Review the fix using [../templates/REVIEW_TEMPLATE.md](../templates/REVIEW_TEMPLATE.md). If the bug report flagged a production directory, this review must use a different model than the one that authored the fix (second-opinion rule, [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) rule 5).
5. Run [../checklists/PRE_COMMIT.md](../checklists/PRE_COMMIT.md).

## What not to do

Do not silently "fix" code beyond the bug's scope while in here — if you find a second, unrelated bug, file a new [../templates/BUG_REPORT_TEMPLATE.md](../templates/BUG_REPORT_TEMPLATE.md) instead of bundling it into this fix. See [../anti-patterns/BAD_ROUTING.md](../anti-patterns/BAD_ROUTING.md) for the general pattern of scope creep routed past the rules meant to catch it.
