# AI Evaluation Standard — Scoring

A fixed rubric for scoring a model's output on a development task, out of 100 points. This is what makes a model swap measurable instead of subjective — see [README.md](README.md) for when to apply it.

## Rubric

| Dimension | Weight | What it measures |
|---|---|---|
| Correctness | 30 | Does the output do what was asked, without defects? |
| Architecture | 15 | Does the output fit the existing design, or does it fight it? |
| Maintainability | 15 | Would a future developer (or model) understand and safely change this output later? |
| Testing | 15 | Is the output adequately covered by tests, or does it reduce confidence in the system? |
| Determinism | 15 | Does the output avoid unnecessary non-determinism (randomness, wall-clock, ordering dependence) per [QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md)? |
| Performance | 10 | Does the output meet reasonable resource/latency expectations for its context? |
| **Total** | **100** | |

Each dimension is scored 0 to its full weight; partial credit is expected and should be justified in one sentence per dimension when recorded.

## Illustrative example — NOT a real measurement

The table below is a worked example showing how the rubric is *applied*, not real evaluation data. No benchmark runs have been recorded yet (see [../benchmarks/README.md](../benchmarks/README.md)); treat every number below as a placeholder demonstrating the scoring mechanics only.

| Model | Correctness (/30) | Architecture (/15) | Maintainability (/15) | Testing (/15) | Determinism (/15) | Performance (/10) | **Total (/100)** |
|---|---|---|---|---|---|---|---|
| Claude *(illustrative)* | 28 | 14 | 14 | 13 | 14 | 9 | **92** |
| Qwen2.5-Coder *(illustrative)* | 24 | 11 | 12 | 14 | 13 | 9 | **83** |
| DeepSeek-Coder *(illustrative)* | 25 | 12 | 13 | 14 | 14 | 9 | **87** |

> These numbers are examples only. Do not cite them in [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md) or [../ai/MODEL_REGISTRY.md](../ai/MODEL_REGISTRY.md) as if they were measured — the matrix's current ratings are explicitly judgment-based for the same reason (see that file's revision history).

## Recording a real score

When a real evaluation is performed:

1. Reference the specific benchmark run(s) from [../benchmarks/<model>/README.md](../benchmarks/) being scored.
2. Fill in the same table shape as above, replacing "(illustrative)" with the actual run date/reference.
3. Justify each dimension's score in one sentence.
4. If the resulting total changes a rating in [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md), update that matrix and note the change in its revision history, citing this scoring record.
