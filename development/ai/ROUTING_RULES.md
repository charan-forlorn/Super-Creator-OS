# Routing Rules

Deterministic task → model routing. Given a task category (see [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md)), this table is the lookup — not a fresh decision each time. Ratings referenced below come from [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md); model details come from [MODEL_REGISTRY.md](MODEL_REGISTRY.md).

## Primary routing table

| Task category            | Primary model | Fallback model | Notes |
|---------------------------|----------------|-----------------|-------|
| Production implementation | Claude         | Qwen2.5-Coder   | Touches `scos/` or other production dirs — highest correctness bar. |
| Architecture               | Claude         | DeepSeek-Coder  | Repo-wide reasoning, cross-module tradeoffs. |
| Large reasoning            | Claude         | DeepSeek-Coder  | Multi-file, multi-step problems with non-obvious dependencies. |
| Debugging (production)    | Claude         | DeepSeek-Coder  | Root-cause work on certified/production modules. |
| Unit tests                 | Ollama (Qwen2.5-Coder) | DeepSeek-Coder | Well-scoped, pattern-following, low ambiguity. |
| Refactoring (non-production) | Ollama (Qwen2.5-Coder) | DeepSeek-Coder | Mechanical, local, reversible — see boundary note below. |
| Documentation              | Ollama (DeepSeek-Coder) | Qwen2.5-Coder | Low-risk, high-volume, no production dependency. |
| Review                     | Claude         | Qwen2.5-Coder   | Judgment-heavy; secondary pass from a different model is encouraged, not routed away from Claude. |
| Planning                   | Claude         | —               | Requires full project context; not delegated. |
| Research                   | Ollama (any)   | Claude          | Exploratory, cheap to redo, low cost of being wrong. |
| Fallback (Claude unavailable) | Ollama (best available) | — | See [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md). |

## Decision rules

When a task doesn't map cleanly onto one row above, apply these rules in order:

1. **Does it touch a production directory** (`scos/`, `source/`, `memory/`, `assets/`, `analytics/`, `rendering/`, `workflow/`, `tests/`) **or change runtime behavior?** → Claude. Production correctness is not delegated by default.
2. **Does it require reasoning across more than 2–3 files, or about non-local tradeoffs** (architecture, performance, security)? → Claude.
3. **Is it mechanical, pattern-following, and fully reversible** (boilerplate tests, doc generation, local refactors with no behavior change)? → Ollama, primary model per the table.
4. **Is the cost of a wrong answer low and easily caught** (exploratory research, a first draft to react to)? → Ollama, any available model.
5. **Is this a re-check of work already done by another model** (a second opinion / adversarial review)? → Route to a *different* model than the one that produced the work, regardless of which table row it falls under.
6. **None of the above resolve it** → default to Claude. Ambiguity itself is a signal that the task needs the model with the broadest context window and the lowest error tolerance.

## Escalation path

Work started on a fallback model that turns out to need rule 1 or 2 above (discovered mid-task, e.g. a "simple" refactor reveals a production dependency) must escalate to Claude before continuing — do not finish production-relevant work on a fallback model only because it was started there. See [FALLBACK_WORKFLOW.md](FALLBACK_WORKFLOW.md) for the handoff procedure.
