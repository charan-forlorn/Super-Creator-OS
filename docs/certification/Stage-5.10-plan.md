# Stage 5.10 Plan - Stage 5 Final AI Command Center Certification

## Requirements

1. Verify Stage 5.1-5.9 source files, contracts, docs, frontend panels, and
   tests exist.
2. Verify Stage 5 workflow continuity (existence/contract only, no
   execution): command bridge -> work session -> adapter contract ->
   prompt/result packet -> operator packet review -> cross-agent router ->
   result intake -> git approval -> manual operator execution runbook.
3. Verify no Stage 5 layer performs real AI dispatch.
4. Verify no network/API/browser/GUI/clipboard automation exists unless
   explicitly allowed by a prior stage contract (the `command_runner.py`
   subprocess allowlist).
5. Verify no backend server, API route, database, WebSocket, polling,
   timer, background worker, CRM, payment, billing, SaaS, or customer
   portal behavior was introduced.
6. Verify the frontend remains static/local mock UI only.
7. Run or document the required Stage 5 tests.
8. Run smoke and security baseline scripts where practical.
9. Produce a deterministic Stage 5 final certification result.
10. Produce a Stage 6 handoff plan.
11. Explicitly close Stage 5 (in the certification narrative doc).
12. Refuse to add new Stage 5 feature work.

## Non-goals

- Does not fix any Stage 5.1-5.9 defect this gate discovers.
- Does not add Stage 5.11+ work - a stage-over-fragmentation scan enforces
  this the same way the Stage 4.19 gate enforced Stage 4's own boundary.
- Does not touch `scos/knowledge` or Stage 4 commercial contracts.

## Architecture

Stage 5.10 is a read-only certification layer over Stage 5:

```
Stage 5.1-5.9 source/contracts/docs/tests/frontend
        v
Stage5FinalCertificationGate (run_stage5_final_certification)
        v
source existence checks -> contract continuity checks -> safety boundary
checks -> frontend static-scope checks -> test evidence checks
        v
Stage 5 final certification result (GO / NO_GO)
        v
Stage 6 handoff plan
```

Two new modules implement it:

- `scos/control_center/stage5_certification_models.py` - immutable
  dataclasses (`Stage5CertificationCheck`, `Stage5CertificationBlocker`,
  `Stage6HandoffItem`, `Stage5FinalCertificationResult`,
  `Stage5FinalCertificationError`) plus a local `FrozenMap`.
- `scos/control_center/stage5_final_certification.py` - the
  `run_stage5_final_certification(...)` gate function itself, mirroring the
  `scos/commercial/stage4_final_release_gate.py` precedent's conventions
  (deterministic id derivation, narrow subprocess exception, bucketed
  readiness scoring, deterministic handoff items).

## Implementation scope

- No new AI orchestration feature; no real AI dispatch; no network; no
  browser/GUI/clipboard automation; no backend server/API/database/
  WebSocket/polling/timers/background workers; no CRM/payment/billing/SaaS.
- Python stdlib only.
- `subprocess` is used only for: read-only `git` queries (informational),
  running each Stage 5 test file, running `scripts/test_smoke.py` and
  `scripts/security_scan_baseline.py`, and optionally `pnpm lint`/`pnpm
  build` from `apps/control-center` (never `pnpm install`).
- The only `__init__.py` change is an append-only block exporting Stage
  5.10's own new public symbols; no existing Stage 5.1-5.9 export is
  reordered, renamed, or removed - including the known duplicate
  `ALLOWED_COMMAND_TYPES` key, which this gate detects but does not fix.

## Test plan

- `scos/control_center/tests/test_stage5_certification_models.py` - model
  immutability, deterministic `to_dict()` key order, enum validation,
  `FrozenMap` round-trip, and the `stage_closed` invariant.
- `scos/control_center/tests/test_stage5_final_certification.py` - a
  temp-directory fixture-repo harness covering: input validation, id
  determinism, GO on a complete fixture, NO_GO on a missing artifact,
  reproduction of the real Stage 5.6 gaps (export coverage, docstring
  convention, frontend wiring, README stray line, duplicate lazy-export
  key), output-artifact stability, safety-scan injection detection, the
  `command_runner.py` subprocess allowlist (`shell=False` passes,
  `shell=True` fails), deterministic Stage 6 handoff items, no mutation of
  the fixture tree, and a final read-only integration pass over the real
  repo.

## Acceptance criteria

- Both test files exit 0 with zero failures.
- Running the gate against a complete synthetic fixture yields `GO`.
- Running the gate against the real repository yields a result object
  (`Stage5FinalCertificationResult`), not an error, with checks and
  blockers correctly reflecting the real repo's state - including the
  known Stage 5.6 defects, which are expected to keep the real run at
  `NO_GO` until they are fixed separately.
- Neither new Python file imports any forbidden token (network, shell
  automation, GUI automation, clipboard automation, `scos.commercial`).
- Neither new frontend file contains any forbidden token or backend-surface
  path marker.

## Risks

- **Known real-repo NO_GO is expected, not a bug.** The Stage 5.6 package
  export gap and the duplicate `ALLOWED_COMMAND_TYPES` lazy-export key are
  real, pre-existing defects; the first real run of this gate is expected
  to certify `NO_GO` because of them. This is documented here explicitly so
  it is not mistaken for a Stage 5.10 implementation defect.
- **Test execution footprint.** Running ~34 Stage 5 test files plus two
  repo scripts via subprocess is a larger footprint than the Stage 4.19
  precedent (2-3 scripts). Each has its own timeout; a hung test cannot
  hang the whole gate indefinitely.
- **`pnpm` availability.** `pnpm lint`/`pnpm build` are skipped (not
  failed) when `pnpm` is unavailable or `node_modules` is not installed, so
  the gate never requires a full frontend toolchain to run.
- **`security_scan_baseline.py` scope gap.** That script's own scope is
  `scos/commercial` + `scripts` + root config; it does not scan
  `scos/control_center` or `apps/control-center`. Stage 5.10's own
  `validate_backend_forbidden_tokens` / `validate_frontend_forbidden_tokens`
  checks are Control Center's only static security coverage today.

## No-overreach checklist

- [x] No real AI dispatch anywhere in the new modules.
- [x] No network/API/browser/GUI/clipboard automation.
- [x] No backend server, API route, database, WebSocket, polling, timer,
      or background worker.
- [x] No CRM/payment/billing/SaaS/customer-portal behavior.
- [x] Frontend stays static/local mock UI only.
- [x] No commit/push/tag/release performed by this stage.
- [x] No Stage 5.1-5.9 public contract broken.
- [x] No Certified Core or Stage 4 public contract changed.
- [x] No new Stage 5.11+ feature work introduced.
