# Example — Review

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))
> **Illustrative only.** The diff referenced below is fictional, used only to demonstrate [../templates/REVIEW_TEMPLATE.md](../templates/REVIEW_TEMPLATE.md)'s shape.

---

**Reviewing:** *(illustrative)* diff adding a new `get_style_by_tag()` method to `scos/memory/style_memory.py`

**Reviewer model:** Claude — second-opinion review since the change touches a production directory ([../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) rule 5), authored by a different model in this illustrative scenario.

**Findings:**

| File | Line | Concern | Severity |
|---|---|---|---|
| `scos/memory/style_memory.py` | *(illustrative)* 88 | New method doesn't validate `tag` is non-empty before querying — inconsistent with existing `get_style()`'s validation pattern at line 41 | non-blocking |
| `scos/memory/tests/test_style_memory.py` | *(illustrative)* — | No test for the empty-tag case | blocking |

**Validation checklist verdict:** fail against [../ai/QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md) — testing dimension not satisfied (missing edge-case coverage).

**Overall verdict:** fail — blocking finding must be resolved before commit, per [../checklists/PRE_COMMIT.md](../checklists/PRE_COMMIT.md).

Contrast with [../anti-patterns/BAD_REVIEW.md](../anti-patterns/BAD_REVIEW.md) for what an inadequate review of this same diff would look like.
