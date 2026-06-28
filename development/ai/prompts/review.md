# Prompt Template — Review

Use for **Review** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Per [ROUTING_RULES.md](../ROUTING_RULES.md) rule 5, the reviewing model must differ from the authoring model when this is a second-opinion pass.

---

**Task:** Review `<diff / file / PR reference>` for correctness, regressions, and design issues.

**Scope:**
- Files/directories under review: `<exact paths>`
- Production directories in scope (if any): `<name them explicitly, or state "none">`

**Constraints:**
- Do not modify the code under review — output findings only, unless explicitly asked to apply fixes.
- Evaluate against [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md)'s checklist, not personal style preference.
- Flag anything that should have escalated per [ROUTING_RULES.md](../ROUTING_RULES.md) (e.g. fallback-authored work touching production) but didn't.

**Acceptance bar:** Every finding states the file/line, the concern, and severity (blocking / non-blocking). No finding without a concrete location.

**Output format:** A list of findings (file, line, concern, severity). End with a pass/fail verdict against the [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md) validation checklist.
