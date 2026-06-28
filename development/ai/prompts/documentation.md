# Prompt Template — Documentation

Use for **Documentation** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Primary model: Ollama (DeepSeek-Coder) per [ROUTING_RULES.md](../ROUTING_RULES.md).

---

**Task:** Write/update documentation for `<exact subject — module, feature, decision>`.

**Scope:**
- Doc file(s) to write/update: `<exact paths>`
- Source of truth being documented: `<exact code paths the docs must accurately reflect>`

**Constraints:**
- Document only what the source actually does — no speculative or aspirational behavior described as current.
- No stub sections; every section is complete (per [QUALITY_GUIDELINES.md](../QUALITY_GUIDELINES.md)).
- Label any illustrative example clearly as an example, never as real measured data (see [evaluation/SCORING.md](../../evaluation/SCORING.md) for the convention).

**Acceptance bar:** A reader unfamiliar with the subject can act on the doc without re-reading the source code; cross-references to other docs resolve correctly.

**Output format:** The complete file content (new file) or a diff (existing file).
