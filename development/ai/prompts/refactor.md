# Prompt Template — Refactor

Use for **Refactoring** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Routed to Ollama by default — escalate to Claude per [ROUTING_RULES.md](../ROUTING_RULES.md) if the refactor turns out to touch a production directory or change observable behavior.

---

**Task:** Refactor `<exact target>` to `<goal — e.g. "remove duplication between X and Y", "extract a helper for Z">` without changing observable behavior.

**Scope:**
- Files/directories in play: `<exact paths>`
- Confirm: does this touch `scos/`, `source/`, `memory/`, `assets/`, `analytics/`, `rendering/`, `workflow/`, or `tests/`? `<yes -> stop and escalate per ROUTING_RULES.md / no -> proceed>`

**Constraints:**
- Behavior must be identical before and after — no test changes unless tests were asserting on the implementation detail being removed.
- No new dependency, no API change.
- Preserve existing naming/structure conventions in the surrounding code.

**Acceptance bar:** All existing tests for the affected area pass unchanged; no behavior diff observable from outside the refactored unit.

**Output format:** A diff/patch against the named files.
