# Template — Benchmark Run Record

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

One-run-record shape, matching the schema in [../benchmarks/README.md](../benchmarks/README.md). Append a filled-in row like this to the matching `development/benchmarks/<model>/README.md` log. See [../examples/benchmark-example.md](../examples/benchmark-example.md) for a worked, explicitly-illustrative instance, and [../anti-patterns/BAD_BENCHMARK.md](../anti-patterns/BAD_BENCHMARK.md) for what not to do.

---

| Field | Value |
|---|---|
| Date | `<actual date the run happened — never backfilled/estimated>` |
| Model | `<Claude / Qwen2.5-Coder / DeepSeek-Coder>` |
| Task category | `<see ../ai/TASK_CLASSIFICATION.md>` |
| Task description | `<short description of the specific task>` |
| Latency | `<wall-clock time, prompt to usable output>` |
| Quality | `<pass/fail against ../ai/QUALITY_GUIDELINES.md, or a score from ../evaluation/SCORING.md>` |
| Pass | `<yes/no — accepted without correction>` |
| Fail reason | `<if applicable>` |
| Token | `<input + output token count, if measurable>` |
| Cost | `<monetary or compute cost, if applicable>` |

Only record runs actually captured at the time they happened — see [../benchmarks/README.md](../benchmarks/README.md).
