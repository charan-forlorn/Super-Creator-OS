# Stage 5 Handoff

Handed off from Stage 4.19 (Stage 4 Final Commercial Release Gate). This
document is design/handoff material only — Stage 4 implemented none of the
Stage 5 workstreams below, and nothing in this document authorizes
retroactive Stage 4 changes.

## Stage 5 objective

Turn the certified, local-first, manual-only Stage 4 commercial foundation
into an operable platform: a real Control Center backend and command API, an
event stream, an operator approval workflow around every outward action,
upgraded release security, and a productized customer workflow — while
preserving the deterministic, evidence-first discipline Stage 4 established.

## Stage 5 non-goals

- Rewriting or breaking Stage 4.1–4.19 public contracts. Stage 4 modules
  stay as the certified execution core; Stage 5 builds around them.
- Fully autonomous outreach or delivery. The operator approval boundary is
  permanent: no send, spend, or customer-facing action without explicit
  human approval.
- Retroactive Stage 4 expansion (see migration rule below).

## What Stage 4 handed off

- A certified commercial pipeline (report → delivery package → CLI →
  orchestrator → acceptance gate → customer kit → monetization review → dry
  run → launch certification → practice lab → outreach kit → prospect
  execution/follow-up/mini-audit/outcome-review → conversion handoff).
- Stage 4.18 hardening assets: shared domain models, unified validation,
  stable manifest/checksum tools, tiered test-suite strategy, security
  hardening baseline, smoke/release/security scripts.
- Design documents awaiting implementation:
  `docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md`,
  `docs/specification/SHARED_REPORTING_FRAMEWORK_CONTRACT.md`.
- The final release gate (`run_stage4_final_release_gate`) and its ten
  deterministic handoff items (`stage5-001` … `stage5-010`), embedded in
  every gate report.

## Recommended Stage 5 workstreams

1. **Control Center backend & command API** (`stage5-001`, `stage5-002`) —
   implement the Stage 4.18 command API design as a local-first backend with
   typed commands, results, and error envelopes.
2. **Event stream** (`stage5-003`) — surface command progress and pipeline
   state changes to the Control Center UI.
3. **Operator approval workflow** (`stage5-004`) — an explicit approve/deny
   step in front of every outward-facing action.
4. **Security upgrades** (`stage5-005`–`stage5-007`) — release provenance
   (machine-readable release reports, branch/HEAD policy), SBOM + dependency
   vulnerability tooling, artifact signing or equivalent integrity.
5. **Customer workflow productization** (`stage5-008`) — turn the
   first-customer pipeline into a repeatable operator playbook with
   templates.
6. **Monitoring & maintenance** (`stage5-009`) — health checks, drift
   detection, and maintenance routines aligned with the test-suite tiers.
7. **Real-integration boundary design** (`stage5-010`) — decide which
   external integrations Stage 5 may build and how each stays behind the
   operator approval boundary.

## Proposed Stage 5 gates

- **Gate 5.A — Command API online**: command API implemented per design;
  contract tests green; still local-first.
- **Gate 5.B — Operator loop closed**: event stream + approval workflow
  working end-to-end for at least one real command.
- **Gate 5.C — Security upgraded**: provenance, SBOM/vulnerability scan, and
  integrity upgrade in the release path.
- **Gate 5.D — Customer workflow productized**: one full customer cycle run
  through the productized workflow with evidence artifacts.
- **Gate 5.E — Stage 5 release gate**: a Stage-5 equivalent of the Stage 4.19
  gate certifies the above before any broader rollout.

## Control Center backend / API implementation path

Start from `CONTROL_CENTER_COMMAND_API_DESIGN.md`; implement the command
registry, request validation (reusing `scos/commercial/validation.py`), and
deterministic result envelopes (reusing the Stage 4.18 domain models);
integrate with the existing UI last. Real integration replaces the Stage 4
design-only stance; nothing may bypass the approval workflow.

## Event stream implementation path

Define an append-only, locally persisted event log first (deterministic,
replayable), then attach a push transport for the UI. The transport choice
(and any WebSocket/polling decision) is a Stage 5 design decision — Stage 4
deliberately shipped no transport.

## Operator approval workflow

Every command that leaves the machine or touches a customer artifact gets a
pending → approved/denied lifecycle with an audit trail, building on the
manual-only flags already enforced by `validate_manual_only_flags`.

## Security upgrades

Extend `scripts/test_release.py` per its Stage 5 notes: machine-readable
release reports, HEAD == origin/main policy, provenance checklist from
`docs/security/SECURITY_HARDENING_BASELINE.md`, then SBOM generation,
dependency vulnerability scanning, and artifact signing.

## Productization / customer workflow path

Consolidate the Stage 4.10–4.17 artifacts into a single operator playbook:
entry criteria, templates, checklists, and evidence requirements per step,
with the conversion handoff as the terminal artifact.

## Monitoring and maintenance plan

Scheduled local runs of the smoke tier and security baseline; drift checks
over contract docs vs. source inventory (the release gate's checks are
reusable for this); a maintenance log under `docs/certification/`.

## Migration rule: no retroactive Stage 4 expansion

Stage 4 is closed. New capability work must never be added as a Stage 4.x
stage — anything tempting to label "Stage 4.20" is by definition Stage 5
backlog, and the Stage 4.19 gate mechanically rejects such markers.
Stage 4 files may change only for genuine defect fixes that preserve the
published contracts.

## Stage 5 acceptance criteria (draft)

- All five proposed gates (5.A–5.E) pass with deterministic evidence
  artifacts.
- Every outward-facing action demonstrably requires operator approval.
- Stage 4 regression suites remain green throughout (no contract breaks).
- Security upgrades active in the release path (provenance + SBOM +
  integrity).
- One real customer cycle completed through the productized workflow with a
  complete evidence chain.
