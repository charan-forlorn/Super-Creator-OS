# Evaluation

How model output gets scored against a fixed rubric ([SCORING.md](SCORING.md)), so that comparing models — or deciding to swap one — is measurable instead of subjective. This is the layer the user flagged as most important: it's what turns [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md)'s judgment-based ratings into evidence-based ones over time.

## When to apply the rubric

- Periodically, against real runs recorded in [../benchmarks/](../benchmarks/), once Phase 5/6 of [../ai/ROADMAP.md](../ai/ROADMAP.md) begins.
- Whenever a model version changes (e.g. a new Qwen2.5-Coder release) — re-score rather than assume the old score still holds.
- Whenever [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md)'s rating for a model/category pair is being revised — the revision should cite a score computed here, not just updated intuition.

## Status

Schema/rubric only. The worked example in [SCORING.md](SCORING.md) is explicitly illustrative, not a real measurement — see that file's labeling convention.

## Relationship to other docs

- Inputs come from [../benchmarks/](../benchmarks/) once populated.
- Outputs feed back into [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md) and, where relevant, [../ai/MODEL_REGISTRY.md](../ai/MODEL_REGISTRY.md)'s Limitations sections.
