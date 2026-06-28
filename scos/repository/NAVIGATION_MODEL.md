# SCOS Repository Navigation Model — Stage 2.9

> Documentation/structural intelligence only. Defines routing, not behavior. Does not
> modify Stage 2 Certified Core or Stage 3.x modules.

```text
TASK INPUT
   |
   v
Task Classifier (by domain keyword/intent)
   |
   v
Route Decision Layer
   |
   +-- Memory Path
   |     entry: scos/memory/style_memory.py (StyleMemoryEngine)
   |     chain: get_style/list_styles -> update_style -> record_video_metrics
   |     exit:  style profile read/written, persisted to scos/work/memory/style_memory.json
   |
   +-- Asset Path
   |     entry: scos/assets/asset_builder_v2.py (AssetBuilderV2) [or asset_builder.py for v1]
   |     chain: style lookup (Memory Path) -> scene_plan -> asset render -> manifest
   |     exit:  manifest + assets written under scos/work/assets|audio|frames
   |
   +-- Render (Video) Path
   |     entry: scos/render/base.py (RenderBackend interface)
   |     chain: ffmpeg_engine.py / video_use_backend.py -> edl_bridge.py -> render output
   |     exit:  rendered artifact under scos/work/render/, RenderResult returned
   |
   +-- Analytics Path
   |     entry: scos/analytics/adapters/base_adapter.py (load/validate/normalize)
   |     chain: adapter -> translator (analytics_translator.py) -> feedback_engine.py
   |             -> learning_coordinator.py -> style_memory.py
   |     exit:  learning_audit.json / style_history.json updated (or REJECT/FAIL, no-op)
   |
   +-- Orchestration Path (Stage 3.x)
   |     entry: scos/pipeline/learning_pipeline.py (single run) or
   |            scos/replay/analytics_replay.py (historical replay)
   |     chain: delegates entirely to the Analytics + Memory + Asset paths above
   |     exit:  pipeline/replay report written under scos/work/pipeline|replay/
   |
   +-- Qualification (QA) Path
         entry: scos/qualification/system_qualification.py
         chain: read-only certification checks across all certified modules
         exit:  certification_report.json (PASS/FAIL), no state mutated
```

## Rules

- Deterministic: a given task classification maps to exactly one path above.
- No ambiguity paths: a task that does not classify into one of the routes above is
  **not** guessed — route it to "needs a Stage 2.9 update" instead of an ad hoc path.
- Every domain has an explicit entry point, processing chain, and exit condition (no
  domain may be routed to without all three being stated).
- Max routing depth: Task Classifier -> Route Decision Layer -> domain entry point = 3 steps.

## Cross-reference

- Agent ownership per domain: [AGENT_CAPABILITY_MATRIX.md](AGENT_CAPABILITY_MATRIX.md)
- Per-task-type entry index: [ENTRY_POINTS.md](ENTRY_POINTS.md)
