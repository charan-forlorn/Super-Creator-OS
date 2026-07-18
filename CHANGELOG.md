# Changelog

## 2026-07-19 — Phase 1.5 (technical-debt clearance)

### Backend / Control Center contract
- **Fixed `_read_surface_metadata` type-mismatch** in
  `scos/control_center/control_center_snapshot.py`
  (`_build_read_surface_sections`). Root cause: the function checked
  `isinstance(result, ReadSurfaceSnapshot)`, but the read-surface facade
  returns a `ReadSurfaceResult` whose records live in `result.snapshot`. The
  check was always `False`, so records stayed empty and
  `approval_summary.status` / `evidence_summary.status` were emitted as
  `UNAVAILABLE` even when the underlying read models contained records.
  Effect: in a healthy repo with traffic files present, the Approvals and
  Evidence panels now correctly surface `AVAILABLE_EMPTY` /
  `AVAILABLE_WITH_DATA` instead of falsely `UNAVAILABLE`. The section JSON
  schema (keys `available`/`status`/`data`/`reason_code`/`observed_at`) and
  the status enum are unchanged — this is a status-value semantics fix, not a
  contract-breaking change. `UNAVAILABLE` still correctly applies when the
  read surface genuinely has no records.
- **Regenerated** `apps/control-center/data/control-center-snapshot.json`
  from the fixed builder so the served (committed) artifact reflects the
  corrected contract. The website route serves this artifact directly, so the
  fix is only live once the artifact is regenerated.
- **Realigned Stage-7 closure gate test assertion**
  (`test_stage7_closure_gate.py::test_optional_runtime_gaps_do_not_downgrade_clean_closure_score`):
  in a HEALTHY repo the optional runtime-artifact warning is correctly absent,
  so the test now asserts the clean closure is not downgraded (rather than
  requiring the stale warning). The missing-artifact warning path remains
  covered by `test_missing_required_artifacts_block_but_optional_runtime_warns`.

### Tests / QA
- Rewired the Python snapshot test fake factory
  (`test_control_center_snapshot.py::_read_surface_result`) to return a real
  `ReadSurfaceResult` wrapping the `ReadSurfaceSnapshot`, matching the facade
  contract. Genuine-failure `UNAVAILABLE` proofs are preserved.
- Realigned every front-end fixture that encoded the buggy `UNAVAILABLE`
  contract for approvals/evidence to the corrected `AVAILABLE_EMPTY` /
  `AVAILABLE_WITH_DATA` values, while keeping explicit genuine-failure
  `UNAVAILABLE` injection tests intact:
  `control-center-truth-contract.test.ts`, `control-center-snapshot.test.ts`,
  `cockpit-bridge.test.tsx`, `control-center-browser-acceptance.test.tsx`,
  `cockpit-routes.test.tsx`, `tests/setup.ts`.
- Added `apps/control-center/scripts/run-tests-local.mjs`: a local Node.js
  runner that executes Vitest headlessly in jsdom (no browser MCP, no external
  egress) and writes `test-report.{json,txt,html}` artifacts into
  `apps/control-center/test-reports/` for the orchestrator to read.

### Docs / evidence
- Created this `CHANGELOG.md`.
- Updated `apps/control-center/docs/phase1-frontend-audit.md` (Data Provenance
  Map) with a clarifying note that approval/evidence sections now report
  `AVAILABLE_*` when data is present. No binding rewrite (schema unchanged).
- Updated `apps/control-center/docs/phase1-browser-acceptance-matrix.md`
  (§2 rule 5, §4 QA results, §4b Phase 1.5 re-verification, §6 open item 1
  resolved).

### Verification
- `pytest scos/control_center`: 100% green.
- `npx vitest run` (control-center): 100% green (0 failed).
- Local-only; no data sent outside the machine.
