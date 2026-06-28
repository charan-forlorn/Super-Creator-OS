# Prompt Template — Architecture

Use for **Architecture** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Primary model: Claude per [ROUTING_RULES.md](../ROUTING_RULES.md) — not delegated to a fallback model except as a second opinion.

---

**Task:** Design `<exact architectural change or decision needed>`.

**Scope:**
- Modules/components affected: `<exact paths/areas>`
- Existing constraints to design within: `<e.g. "must not modify Certified Core", named explicitly per project>`

**Constraints:**
- Identify and reuse existing patterns before proposing new abstractions.
- State tradeoffs explicitly — do not present one option as obviously correct without naming what was considered and rejected.
- Flag anything that would require a production-directory change so it can be confirmed against [ROUTING_RULES.md](../ROUTING_RULES.md) before implementation starts.

**Acceptance bar:** The design names the files to be created/changed, the interfaces between affected components, and a verification plan — sufficient for an implementation task (see [coding.md](coding.md)) to be written directly from it.

**Output format:** A written design (prose + structure, not code) — file paths named explicitly, no enumeration of every line.
