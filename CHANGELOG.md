# Changelog

## 2026-07-19 — Phase 2 Security Sign-off (net-new local-first routes)

Operator (Nott) reviewed and approved two net-new Phase 2 route boundaries for
registration in the security allowlist (`_REVIEWED_ROUTES` in
`scos/control_center/tests/test_file_snapshot_refresh_transport.py`):

- **`apps/control-center/app/api/brand-kit/route.ts`** — Brand Kit authoritative
  transport (GET/POST). Same-origin, local-first boundary with a strict
  `ALLOWED_FIELDS` allow-list, bounded 8192-byte body, unexpected-field
  rejection, and fail-closed persistence to a dedicated brand-kit store. No
  subprocess, no external network, no write to `memory/database.json`.
- **`apps/control-center/app/api/hvs-render/export/route.ts`** — Export Package
  endpoint, registered as a **controlled fail-closed stub**. Returns
  `EXPORT_NOT_READY` (409) unless `SCOS_EXPORT_STUB_ENABLED=1`, which only yields
  a deterministic `data:` URL + sha256 envelope for the Golden Project E2E
  test-double. No subprocess, no network, no mutation, no `memory/database.json`
  write. The real Python export backend remains unbuilt; this route is inert by
  design until then.

Effect: the security gate test
`test_no_forbidden_runtime_source_markers_and_no_frontend_route_files` now passes
(previously `FAILED` because these two routes were unreviewed). Both routes follow
project discipline (Bounded Payload, Controlled Fail-closed Stub).

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

## 2026-07-19 — Phase 2 (Solo Operator MVP) — net-new UI + E2E gate

### Scope note (important)
The Safe Subprocess Bridge, HVS Materialization routes, and Explicit Operator
Confirmation were already built and security-reviewed in prior cohorts (10C/10E)
and live in the working tree (untracked). Phase 2 therefore adds the **net-new**
Solo Operator surface on top of that foundation: Create Project Wizard, Brand
Kit, the explicit confirmation dialog, the Export-Package seam, the Golden
Project E2E test, and the No-Terminal acceptance gate.

### Frontend (Team-A)
- **Create Project Wizard** (`app/projects/new/page.tsx`,
  `components/create-project-wizard.tsx`, `components/wizard/*`): 5-step state
  machine (Brief → Template → Assets → Output Profiles → Confirm) reusing
  `validateProjectDraft` + `OUTPUT_PROFILES`. Server-resolved paths only; the
  wizard emits profile ids, never filesystem paths. `aria-current="step"` +
  focus-on-step-enter + `role="alert"` validation.
- **Brand Kit** (local-only, server-resolved): `lib/brand-kit.ts`,
  `lib/brand-kit-store.ts` (atomic-write mirror of `project-preparation-store.ts`,
  same `memory/runtime/control-center/brand-kit-v1.json` anchor),
  `app/api/brand-kit/route.ts` (GET+POST, allow-list, fail-closed),
  `lib/brand-kit-client.ts` (`useBrandKit`), `components/brand-kit-editor.tsx`,
  `app/brand-kit/page.tsx`.
- **Explicit Operator Confirmation** (`components/confirmation-modal.tsx`):
  accessible `role="dialog"` + `aria-modal`, focus trap, ESC/backdrop cancel,
  single explicit confirm button. Wired in front of `HvsRenderPanel` execute
  (the underlying checkbox + disabled-execute gate already existed). Hard rule:
  no auto-execute on mount/timeout/focus-loss/backdrop.

### Backend bridge (Team-B)
- **Export-Package seam** (`app/api/hvs-render/export/route.ts` +
  `exportRenderArtifact` in `lib/hvs-render-client.ts`): fail-closed stub.
  Returns a deterministic package envelope ONLY when `SCOS_EXPORT_STUB_ENABLED=1`
  (Golden Project E2E test-double). Otherwise refuses (`EXPORT_NOT_READY`) so the
  UI export control stays **inert** — no fabricated success. Rationale: a real
  Python export backend does not yet exist (the HVS adapter allowlist forbids the
  export operation); real export is deferred to a later phase.

### Tests / QA (Team-C)
- `tests/phase2-happy-path.test.tsx`: Golden Project through real components
  (wizard draft → render confirm → execute → export test-double), via `fetch`
  stub at the boundary (no real Python/network).
- `tests/phase2-negative-paths.test.tsx`: asset-missing, schema-error,
  system-unavailable, unexpected-field — each asserts a **visible** (non-silent)
  classification.
- `tests/phase2-a11y-baseline.test.tsx`: dialog semantics + disabled-until-confirm.
- `tests/phase2-render-double-store.test.ts`: bridge-layer double (fake child
  process) proving the single-spawn, no-shell, deterministic-package seam.
- `tests/phase2-protected-repo-guard.test.ts` (Team-D): asserts Phase-2 activity
  mutates no protected HVS files (`memory/database.json`,
  `scos/control_center/control_center_snapshot.py`, learning archive).
- `scripts/run-tests-local.mjs`: added `--phase2` (curated manifest) and `--gate`
  (exits 2 on RED) flags. `scripts/phase2-acceptance.sh` runs both legs.

### Docs / evidence (Team-D)
- This entry + Data Provenance Map note: Brand Kit store sits in
  `memory/runtime/control-center/` (runtime only), never `memory/database.json`
  or the learning archive. Export is a controlled stub until a real backend lands.

### Verification
- `node apps/control-center/scripts/run-tests-local.mjs --phase2 --gate` →
  100% green (Phase-2 suites).
- `uv run pytest scos/control_center/tests/test_control_center_snapshot.py
  scos/control_center/tests/test_stage7_closure_gate.py -q` → green.
- Local-only; no data sent outside the machine.
