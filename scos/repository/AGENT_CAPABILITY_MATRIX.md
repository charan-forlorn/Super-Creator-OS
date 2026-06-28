# SCOS Agent Capability Matrix — Stage 2.9

> Documentation/structural intelligence only. Defines responsibility, not behavior. Does
> not modify Stage 2 Certified Core or Stage 3.x modules.

## Matrix

| Agent | Read Access | Write Access | Ownership | Dependencies |
|---|---|---|---|---|
| Orchestrator | all domains | none (delegates only) | execution flow only | none |
| Requirement Analyst | all domains | `scos/repository/` docs only | task classification accuracy | Orchestrator |
| Solution Designer | all domains | none (proposes only) | architecture decisions | Requirement Analyst |
| Code Generator | scoped to assigned domain | scoped to assigned domain, non-certified files only | implementation correctness | Solution Designer |
| Testing Agent | scoped to assigned domain + its tests | test files only | test coverage | Code Generator |
| Deployment Agent | build/release config | release artifacts only | release execution | Testing Agent |
| Monitoring Agent | runtime state, logs | none (read-only) | observability | none (independent) |
| Optimization Agent | performance/profiling data | non-certified perf-tuning code only | efficiency, never correctness | Testing Agent (validation chain) |

## Strict rules

- Orchestrator = owns execution flow only.
- Code Generator = cannot change architecture.
- Monitoring = read-only on runtime state.
- Optimization = cannot bypass the validation chain.
- No agent role, regardless of write access, may modify Stage 2 Certified Core
  (`scos/assets/asset_builder.py`, `scos/assets/asset_builder_v2.py`,
  `scos/memory/style_memory.py`, `scos/analytics/feedback_engine.py`,
  `scos/learning/learning_coordinator.py`, `scos/learning/learning_policy.py`,
  `scos/qualification/system_qualification.py`, `scos/render/base.py`) or any Stage 3.x
  orchestrator (`scos/pipeline/learning_pipeline.py`, `scos/replay/analytics_replay.py`).
  Write access above is scoped to non-certified surrounding code only.

## Dependency graph

```text
Code Generator -> Solution Designer -> Requirement Analyst -> Orchestrator
Testing Agent -> Code Generator
Deployment Agent -> Testing Agent
Optimization Agent -> Testing Agent
Monitoring Agent (independent, no dependency edge)
```

## Cross-reference

- Domain routing: [NAVIGATION_MODEL.md](NAVIGATION_MODEL.md)
- Per-task-type entry index: [ENTRY_POINTS.md](ENTRY_POINTS.md)
