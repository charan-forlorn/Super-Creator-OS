# SCOS Entry Points — Stage 2.9

> Documentation/structural intelligence only. No task type may begin without consulting
> this file first. Does not modify Stage 2 Certified Core or Stage 3.x modules.

```text
TASK TYPE: QA
ENTRY POINT: scos/qualification/system_qualification.py
FLOW: Capability Check -> Evidence Collection -> Validation Rules -> Execution Plan

TASK TYPE: MEMORY
ENTRY POINT: scos/memory/style_memory.py
FLOW: Schema Validation -> Database Access (StyleMemoryEngine) -> Retrieval Layer -> Response Builder

TASK TYPE: ASSETS
ENTRY POINT: scos/assets/asset_builder_v2.py
FLOW: Style Lookup -> Scene Plan Resolution -> Asset Render -> Manifest Write

TASK TYPE: RENDER (VIDEO)
ENTRY POINT: scos/render/base.py
FLOW: Backend Selection -> FFmpeg/Video-Use Pipeline -> EDL Bridge -> Render Output

TASK TYPE: ANALYTICS
ENTRY POINT: scos/analytics/adapters/base_adapter.py
FLOW: Adapter Load/Validate/Normalize -> Translation -> Feedback Scoring -> Learning Coordination

TASK TYPE: LEARNING
ENTRY POINT: scos/learning/learning_coordinator.py
FLOW: Policy Evaluation -> Safety Enforcement -> Style Update -> Audit Persistence

TASK TYPE: ORCHESTRATION (single run)
ENTRY POINT: scos/pipeline/learning_pipeline.py
FLOW: Load -> Validate -> Translate -> Feedback -> Coordinate -> Assets -> Report

TASK TYPE: ORCHESTRATION (historical replay)
ENTRY POINT: scos/replay/analytics_replay.py
FLOW: Load (one/many) -> Per-record Process -> Aggregate -> Report
```

## Strict requirement

No task type may start without an entry point above. This file, combined with
[NAVIGATION_MODEL.md](NAVIGATION_MODEL.md), prevents random-access architecture: an agent
should never need to read the full repository to know where to start.

## Cross-reference

- Domain routing: [NAVIGATION_MODEL.md](NAVIGATION_MODEL.md)
- Agent ownership per domain: [AGENT_CAPABILITY_MATRIX.md](AGENT_CAPABILITY_MATRIX.md)
