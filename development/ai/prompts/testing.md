# Prompt Template — Testing

Use for **Testing** tasks (see [TASK_CLASSIFICATION.md](../TASK_CLASSIFICATION.md)). Primary model: Ollama (Qwen2.5-Coder) per [ROUTING_RULES.md](../ROUTING_RULES.md).

---

**Task:** Write/extend tests for `<exact behavior or module>` covering `<list specific cases — happy path, edge cases, failure modes>`.

**Scope:**
- Code under test: `<exact paths>`
- Test file(s) to write/extend: `<exact paths>`

**Constraints:**
- Match the existing test framework/convention used in this codebase (check the surrounding test directory before assuming pytest, plain-assert scripts, etc.).
- No change to the code under test — tests only, unless a bug is found, in which case stop and report it rather than silently "fixing" production code from a testing task.
- Deterministic: no reliance on wall-clock time, network, or unseeded randomness.

**Acceptance bar:** New/changed tests pass; running the full existing suite for this module shows zero regressions.

**Output format:** A diff/patch against the named test file(s), plus the command used to run them and its result.
