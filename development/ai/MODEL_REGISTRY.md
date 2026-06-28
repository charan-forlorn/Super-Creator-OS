# Model Registry

Supported models for SCOS development, with strengths, weaknesses, best use cases, limitations, and recommended tasks. Comparable ratings live in [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md); routing decisions built on this registry live in [ROUTING_RULES.md](ROUTING_RULES.md).

## Claude (primary model)

- **Strengths:** broadest context window in active use, strongest multi-file/repo-wide reasoning, highest reliability on production-correctness work, best judgment on ambiguous or under-specified tasks, strongest architecture and review capability.
- **Weaknesses:** cloud-dependent (the single point of failure this whole layer exists to mitigate), highest cost per task, subject to outages/rate limits outside SCOS's control.
- **Best use cases:** production implementation, architecture, large/multi-step reasoning, debugging certified modules, planning, review.
- **Limitations:** none unique to capability within current routing scope; the only structural limitation is availability, which is why a fallback path exists at all.
- **Recommended tasks:** see "Primary model: Claude" rows in [ROUTING_RULES.md](ROUTING_RULES.md).

## Qwen2.5-Coder (local, via Ollama)

- **Strengths:** strong at code-pattern-following tasks (unit tests, boilerplate, mechanical refactors), runs fully local, no per-token cost, no outage risk tied to a remote vendor.
- **Weaknesses:** smaller effective context window than Claude, weaker at cross-file architectural reasoning, more likely to need a second pass on ambiguous requirements.
- **Best use cases:** unit test generation, local/non-production refactors, fallback production work when escalation to Claude is not yet possible.
- **Limitations:** should not be the final word on production-correctness decisions without review (see [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md)); local hardware constrains model size and therefore ceiling capability.
- **Recommended tasks:** unit tests (primary), refactoring (primary), production implementation (fallback only).

## DeepSeek-Coder (local, via Ollama)

- **Strengths:** strong at documentation generation and explaining existing code, competitive reasoning for its size, good secondary-opinion model for review/adversarial checks.
- **Weaknesses:** like Qwen2.5-Coder, smaller context window than Claude; less consistent than Claude on tasks requiring sustained multi-file state tracking.
- **Best use cases:** documentation (primary), unit tests (fallback), architecture/large-reasoning/debugging (fallback opinions, not primary authorship).
- **Limitations:** not routed as a primary for production implementation or architecture in v1 — treated as a fallback/second-opinion model until evidence in `../benchmarks/deepseek/` and a score in `../evaluation/SCORING.md` justifies more.
- **Recommended tasks:** documentation (primary), research (any), second-opinion review.

## Future models

Placeholder section. To onboard a new model:

1. Add a registry entry here in the same shape (Strengths / Weaknesses / Best use cases / Limitations / Recommended tasks).
2. Add a column to [AI_CAPABILITY_MATRIX.md](AI_CAPABILITY_MATRIX.md).
3. Create `../benchmarks/<model>/README.md` following the existing schema.
4. Decide, using [ROUTING_RULES.md](ROUTING_RULES.md)'s decision rules, whether the new model becomes a primary for any task category or starts as fallback-only.

No restructuring of this document or of routing is required to add a model — see [DEVELOPMENT_AI_LAYER.md](DEVELOPMENT_AI_LAYER.md)'s "Future extensibility" section.
