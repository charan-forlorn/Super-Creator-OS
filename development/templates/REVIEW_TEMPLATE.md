# Template — Review

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

Structured review output shape, extending [../ai/prompts/review.md](../ai/prompts/review.md) into a fill-in document. See a worked example at [../examples/review-example.md](../examples/review-example.md) and a violation example at [../anti-patterns/BAD_REVIEW.md](../anti-patterns/BAD_REVIEW.md).

---

**Reviewing:** `<diff / file / PR reference>`

**Reviewer model:** `<must differ from authoring model if this is a second-opinion review — see ../ai/ROUTING_RULES.md rule 5>`

**Findings:**

| File | Line | Concern | Severity (blocking / non-blocking) |
|---|---|---|---|
| | | | |

**Validation checklist verdict:** pass/fail against [../ai/QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md)'s checklist — `<state which items failed, if any>`

**Overall verdict:** `<pass / fail>`
