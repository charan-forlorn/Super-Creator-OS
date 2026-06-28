# Example — Feature Walkthrough

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))
> **Illustrative only.** The feature below ("style-tag search in StyleMemory") is fictional, used only to demonstrate the template/playbook shapes — it has not been built and this is not a real task record.

A worked example of [../templates/TASK_TEMPLATE.md](../templates/TASK_TEMPLATE.md) following [../playbooks/START_NEW_FEATURE.md](../playbooks/START_NEW_FEATURE.md).

---

**Task category:** Implementation (production) — per [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md)

**Routed model:** Claude — per [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md), since this touches `scos/memory/style_memory.py` (a production directory), routing rule 1 applies regardless of perceived task size.

**Scope:**
- Files/directories in play: `scos/memory/style_memory.py`, `scos/memory/tests/test_style_memory.py` *(illustrative paths)*
- Production directories touched: `scos/memory/` — yes, explicitly named.

**Constraints:**
- No new dependency.
- No change to `StyleMemoryEngine`'s existing public method signatures — only a new method added.
- Deterministic: no randomness, no wall-clock dependence in the new lookup logic.

**Acceptance bar:**
- New method has test coverage in the existing suite with zero regressions to existing tests.

**Playbook trace:**
1. Classified per [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md) → Implementation (production).
2. Routed per [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) and confirmed via [../checklists/MODEL_SELECTION.md](../checklists/MODEL_SELECTION.md) → Claude (production-directory branch).
3. This template filled in (above).
4. [../checklists/PRE_IMPLEMENTATION.md](../checklists/PRE_IMPLEMENTATION.md) run — all items checked.
5. Implemented via [../ai/workflows/claude.md](../ai/workflows/claude.md).
6. [../checklists/PRE_COMMIT.md](../checklists/PRE_COMMIT.md) run — tests pass, no unintended diff outside `scos/memory/`.
7. [../checklists/PRE_PR.md](../checklists/PRE_PR.md) run before opening the (illustrative) PR.
