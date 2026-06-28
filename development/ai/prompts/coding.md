# Prompt Template — Coding

Use for **Implementation** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Follows the structure required by [PROMPT_STANDARDS.md](../PROMPT_STANDARDS.md).

---

**Task:** Implement `<one-sentence description of the behavior being added or changed>`.

**Scope:**
- Files/directories in play: `<exact paths>`
- Production directories touched (if any): `<name them explicitly, or state "none">`

**Constraints:**
- No new dependencies unless explicitly listed here: `<list, or "none">`
- No change to public API/signatures unless stated: `<state if applicable>`
- Must remain deterministic / no new randomness or wall-clock dependence: `<yes/no, applicable systems only>`
- Reuse existing patterns/utilities at: `<paths, if known>`

**Acceptance bar:**
- `<e.g. "existing test suite at <path> passes with zero regressions">`
- `<e.g. "new behavior covered by a test in the same change">`

**Output format:** A diff/patch against the named files, or new file(s) at the named paths. No explanation needed beyond what's in code comments justified by [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md) (comment only non-obvious WHY, not WHAT).
