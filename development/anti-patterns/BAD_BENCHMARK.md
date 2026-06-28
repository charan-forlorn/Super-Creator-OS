# Anti-pattern — Bad Benchmark

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

What not to do, contrasted with [../templates/BENCHMARK_TEMPLATE.md](../templates/BENCHMARK_TEMPLATE.md) and [../benchmarks/README.md](../benchmarks/README.md).

## Bad example

> | Date | Model | Task | Latency | Quality | Pass | Token | Cost |
> |---|---|---|---|---|---|---|---|
> | (backfilled, ~last week) | Claude | "general coding stuff" | "fast" | "good" | yes | ~2000 | "cheap" |

## Why this is bad

- **Backfilled/estimated, not captured at the time** — [../benchmarks/README.md](../benchmarks/README.md) and every `development/benchmarks/<model>/README.md` explicitly require runs to be logged when they actually happen, not reconstructed from memory afterward.
- **Vague task description** — "general coding stuff" doesn't map to a [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md) category, making the row useless for the evidence chain in [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md).
- **Non-numeric, unverifiable fields** — "fast," "good," "cheap" aren't measurements; [../templates/BENCHMARK_TEMPLATE.md](../templates/BENCHMARK_TEMPLATE.md) expects actual latency/cost values or an explicit "not measured" rather than a qualitative guess presented as data.

## The fix

Only log a row at the time a run is actually captured, using [../templates/BENCHMARK_TEMPLATE.md](../templates/BENCHMARK_TEMPLATE.md)'s exact fields, with real values or an explicit "not measured" — never a vague approximation standing in for a number. See [../examples/benchmark-example.md](../examples/benchmark-example.md) for the correctly-labeled illustrative version of this template.
