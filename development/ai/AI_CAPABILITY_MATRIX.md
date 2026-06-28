# AI Capability Matrix

A rated comparison of model capability per task category, so SCOS can choose a model from data instead of impression. This matrix is the evidence [ROUTING_RULES.md](ROUTING_RULES.md)'s decision table is built on, and the categories match [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md). Model-level detail (why a rating is what it is) lives in [MODEL_REGISTRY.md](MODEL_REGISTRY.md).

## Rating scale

⭐ (1) weak — not recommended for this task category
⭐⭐ (2) below average — usable only with heavy review
⭐⭐⭐ (3) adequate — usable as a fallback
⭐⭐⭐⭐ (4) strong — usable as a primary in most cases
⭐⭐⭐⭐⭐ (5) excellent — preferred primary

These are **initial, judgment-based ratings** pending real evidence. As `../benchmarks/` accumulates runs and `../evaluation/SCORING.md` produces scores, update the cells below and note the change in this file's revision history.

## Matrix

| Task                  | Claude | Qwen2.5-Coder | DeepSeek-Coder |
|------------------------|--------|----------------|------------------|
| Architecture           | ⭐⭐⭐⭐⭐ | ⭐⭐⭐           | ⭐⭐⭐⭐            |
| Implementation (production) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐          | ⭐⭐⭐             |
| Refactor               | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐         | ⭐⭐⭐⭐⭐           |
| Unit Test              | ⭐⭐⭐⭐  | ⭐⭐⭐⭐⭐         | ⭐⭐⭐⭐⭐           |
| Review                 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐           | ⭐⭐⭐⭐            |
| Debugging              | ⭐⭐⭐⭐⭐ | ⭐⭐⭐           | ⭐⭐⭐⭐            |
| Documentation          | ⭐⭐⭐⭐  | ⭐⭐⭐⭐          | ⭐⭐⭐⭐⭐           |
| Repository Analysis    | ⭐⭐⭐⭐⭐ | ⭐⭐            | ⭐⭐⭐             |
| Planning               | ⭐⭐⭐⭐⭐ | ⭐⭐            | ⭐⭐⭐             |
| Research               | ⭐⭐⭐⭐  | ⭐⭐⭐⭐          | ⭐⭐⭐⭐            |

## How to read this matrix

- A 5-star cell is a candidate primary for that task category, subject to [ROUTING_RULES.md](ROUTING_RULES.md)'s decision rules (rules 1–2 route production-touching and architectural work to Claude regardless of how close the stars are).
- A tie between models (e.g. Refactor, Unit Test) means routing is decided by *availability and cost*, not capability — prefer the local model when capability ties, to conserve Claude usage for work only Claude is rated highest for.
- Ratings below ⭐⭐⭐ for a category mean: do not use that model as a primary, and review any fallback output from it more carefully (see [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md)).

## Revision history

- v1 (initial): judgment-based ratings, no benchmark/evaluation evidence yet. Future updates should reference the specific benchmark runs or evaluation scores that justified a changed rating.
