# Premium Control Center Research — 2026-09-19

## Design inputs
- Linear design refresh: reduce visual competition, quieter chrome, softer structure, compact navigation, tokenized design.
- Datadog dashboards: focus on recurring operational questions, priorities, issues, and outcomes; avoid cramming unrelated metrics together.
- GitHub Actions deployment views: pair status with environment, source commit/PR, duration, workflow/logs, and approval state.
- Agent control-center patterns: live status, approval queue, audit trail, intervention points, risk/context, and drill-down.
- Agent Skills standards: SKILL.md plus optional references/scripts/assets, progressive disclosure, routing metadata, explicit permissions, and quality controls.
- Skill-quality research: routing metadata, bloated skill bodies, and weak organization are common failure modes; validate skill discoverability and boundaries.

## Application to HAIOS/SCOS
Mission Control should prioritize:
Overview → Runs → Skills → Approvals → Evidence → Systems

The design should feel like an operations instrument rather than a marketing dashboard:
- one dominant signal;
- compact cards and tables;
- calm neutrals with disciplined status colors;
- clear currentness;
- visible evidence/provenance;
- explicit Human intervention boundaries;
- drill-down instead of excessive simultaneous detail.

## Local reusable foundation discovered
- scos/control_center/control_center_snapshot.py: authoritative read-only projection.
- apps/control-center/lib/control-center-snapshot.ts: truth-state mapping contract.
- apps/control-center/app/api/control-center-snapshot/route.ts: local read-only transport.
- operator-read-surface-projection/types: operator signal/coherence model.
- phase1 browser/provenance docs: acceptance and data-source mapping.
These are preserved as extraction artifacts before retirement of the legacy frontend.
