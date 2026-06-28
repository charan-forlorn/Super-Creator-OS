# Task Classification

Categories of software engineering work and the recommended model for each. This is the input to [ROUTING_RULES.md](ROUTING_RULES.md) — classify the task first, then look up the model.

| Category | Definition | Recommended model | Cross-reference |
|---|---|---|---|
| **Architecture** | Designing or changing how modules/components fit together; cross-module tradeoffs. | Claude | [ROUTING_RULES.md](ROUTING_RULES.md), [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md) |
| **Implementation** | Writing new code or changing existing code to a specified behavior, including production modules. | Claude (production) / Ollama (non-production) | [ROUTING_RULES.md](ROUTING_RULES.md) |
| **Testing** | Writing or extending unit/integration tests against an already-defined behavior. | Ollama (Qwen2.5-Coder) | [prompts/testing.md](prompts/testing.md) |
| **Review** | Evaluating existing code/diffs for correctness, regressions, or design issues. | Claude (primary), second-opinion from any model | [prompts/review.md](prompts/review.md) |
| **Debugging** | Diagnosing the root cause of a defect, possibly across multiple files. | Claude (production) / Ollama fallback for non-production | [ROUTING_RULES.md](ROUTING_RULES.md) |
| **Documentation** | Writing or updating explanatory docs, READMEs, or inline documentation. | Ollama (DeepSeek-Coder) | [prompts/documentation.md](prompts/documentation.md) |
| **Refactoring** | Restructuring code without changing observable behavior. | Ollama (Qwen2.5-Coder), escalate to Claude if production-touching | [prompts/refactor.md](prompts/refactor.md) |
| **Planning** | Deciding what to build and in what order; requires full project context. | Claude only | [DEVELOPMENT_AI_LAYER.md](DEVELOPMENT_AI_LAYER.md) |
| **Research** | Exploratory investigation where being wrong is cheap and easily caught. | Ollama (any) | [ROUTING_RULES.md](ROUTING_RULES.md) |

## Classifying ambiguous work

If a task spans more than one category (e.g. "refactor and document this module"), split it into separate tasks per category before routing — see [PROMPT_STANDARDS.md](PROMPT_STANDARDS.md)'s anti-patterns section. Each piece then routes independently, and a refactor that turns out to touch a production module escalates per [ROUTING_RULES.md](ROUTING_RULES.md) regardless of what the rest of the original request was.
