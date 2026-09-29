# Premium Control Center Research — 2026-09-19

## Design inputs
- Linear: reduce visual competition, quiet chrome, softer structure, compact navigation, tokenized design.
- Datadog: focus dashboards on recurring operational questions, priorities, issues, and outcomes.
- GitHub Actions: pair status with environment, source commit/PR, duration, workflow/logs, and approval state.
- Agent control-center patterns: live status, approval queues, audit trails, intervention points, risk/context, and drill-down.
- Agent Skills standards: SKILL.md plus optional references/scripts/assets, progressive disclosure, routing metadata, permissions, and quality controls.
- Skill-quality research: weak routing metadata, bloated skill bodies, and poor organization are common failure modes.

## Mission Control information architecture
Overview -> Runs -> Skills -> Approvals -> Evidence -> Systems

The UI should answer:
1. What is happening now?
2. What changed?
3. What needs attention?
4. What evidence supports the state?
5. What can the Human safely do next?

## Premium visual direction
- calm mission-control instrument, not a wall of charts;
- one dominant accent plus restrained neutrals;
- compact operational density;
- strong typography hierarchy;
- drill-down instead of simultaneous detail overload;
- visible LIVE/EMPTY/DEGRADED/UNKNOWN semantics;
- responsive desktop/mobile layouts.

## Reusable legacy foundation preserved
- control-center snapshot contract and adapter;
- operator read-surface projection/types;
- phase-1 browser acceptance matrix;
- phase-1 frontend provenance audit;
- scos-control-center-ui skill.

## Architecture
Floot Mission Control is presentation-only and bounded.
Hermes remains Primary Operator.
HAIOS remains governance/currentness/evidence/approval authority.
SCOS remains media/telemetry/provenance/learning authority.
No Floot-local state grants execution authority.
