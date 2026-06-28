# Anti-pattern — Bad Prompt

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

What not to do, contrasted with [../ai/prompts/coding.md](../ai/prompts/coding.md) and [../ai/PROMPT_STANDARDS.md](../ai/PROMPT_STANDARDS.md).

## Bad example

> "Can you improve the analytics module? Make it better and also add some tests and maybe update the docs while you're at it. Use your best judgment."

## Why this is bad

- **Open-ended, not deterministic** — "improve" and "make it better" have no stated scope or acceptance bar. Violates [PROMPT_STANDARDS.md](../ai/PROMPT_STANDARDS.md)'s "deterministic" requirement.
- **Mixes task categories** — implementation, testing, and documentation are bundled into one prompt. Violates the anti-pattern explicitly called out in [PROMPT_STANDARDS.md](../ai/PROMPT_STANDARDS.md): split per category so each piece routes correctly per [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md).
- **No acceptance bar** — "done" is left entirely to the model's judgment, which defeats reproducibility.
- **No scope** — doesn't name which files/directories are in play, or whether a production directory is touched (relevant to [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md)'s routing decision).

## The fix

Split into three prompts using [../ai/prompts/coding.md](../ai/prompts/coding.md), [../ai/prompts/testing.md](../ai/prompts/testing.md), and [../ai/prompts/documentation.md](../ai/prompts/documentation.md) respectively, each filling in Task / Scope / Constraints / Acceptance bar / Output format per [PROMPT_STANDARDS.md](../ai/PROMPT_STANDARDS.md)'s required structure. Each piece then routes to its own model independently per [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md).
