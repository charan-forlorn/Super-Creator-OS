# Anti-pattern — Bad Review

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

What not to do, contrasted with [../templates/REVIEW_TEMPLATE.md](../templates/REVIEW_TEMPLATE.md) and [../examples/review-example.md](../examples/review-example.md).

## Bad example

> "Looks fine, ship it."

## Why this is bad

- **No file/line reference** — a finding (or absence of findings) must be anchored to a location; "looks fine" reviews nothing in particular.
- **No severity** — [REVIEW_TEMPLATE.md](../templates/REVIEW_TEMPLATE.md) requires blocking/non-blocking classification for every finding; this has none.
- **No verdict against the checklist** — doesn't state whether [../ai/QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md)'s validation checklist was actually run, or just assumed.
- **Same-model review presented as a second opinion** — if this was meant to satisfy [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) rule 5 (second-opinion review), a one-line rubber stamp doesn't demonstrate independent judgment was applied.

## The fix

Use [../templates/REVIEW_TEMPLATE.md](../templates/REVIEW_TEMPLATE.md) in full: a findings table (even if empty, state that explicitly and why), a checklist verdict, and an overall pass/fail. See [../examples/review-example.md](../examples/review-example.md) for the filled-in shape.
