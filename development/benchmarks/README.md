# Benchmarks

An empty, structured place to log real development-task runs per model over time, so SCOS can eventually learn — from evidence, not impression — which model performs best on which kind of task. This directory is referenced by [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md) (ratings should eventually be justified by data recorded here) and is the input to [../evaluation/SCORING.md](../evaluation/SCORING.md).

## Status

This is **schema-only scaffolding**. No benchmark runs have been recorded yet — see [../ai/ROADMAP.md](../ai/ROADMAP.md) Phase 5 ("Performance Benchmark"), which is not yet underway. Nothing in `claude/`, `qwen/`, or `deepseek/` represents a real measurement.

## Structure

```text
benchmarks/
  claude/README.md      <- schema + log for Claude runs
  qwen/README.md        <- schema + log for Qwen2.5-Coder runs
  deepseek/README.md     <- schema + log for DeepSeek-Coder runs
```

## Recorded fields (schema)

Every run, once Phase 5 begins, should record:

| Field | Meaning |
|---|---|
| Task | Which [TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md) category, plus a short description of the specific task. |
| Latency | Wall-clock time from prompt submission to usable output. |
| Quality | Pass/fail against [QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md), or a [SCORING.md](../evaluation/SCORING.md) score if one was computed. |
| Pass | Whether the output was accepted without correction. |
| Fail | Whether the output required correction or rejection, and why. |
| Token | Token count consumed (input + output), where applicable/measurable. |
| Cost | Monetary or compute cost of the run, where applicable. |

## How this gets used

Once enough runs are recorded per model per task category, that data should replace the judgment-based ratings in [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md) and feed [../evaluation/SCORING.md](../evaluation/SCORING.md)'s rubric with real inputs instead of illustrative examples — see [../ai/ROADMAP.md](../ai/ROADMAP.md) Phases 5–6.
