# Stage 6.7 Certification — Frontend Test Tier (apps/control-center)

**Status:** IMPLEMENTED — READY FOR COMMIT (no push)
**Date:** 2026-07-08
**Branch:** main
**Scope:** Add an automated, offline frontend test tier for `apps/control-center`
  (Vitest + Testing Library + jsdom). Plus a requested customer-side wiring:
  customer "🚩 รายงานข้อผิดพลาด" button -> `POST /api/report-error` -> operator
  error-report page in `api_handler.py`.

> NOTE: A separate, pre-existing untracked `docs/certification/Stage-6.7-plan.md`
> already covers a DIFFERENT 6.7 topic ("Wire Approval Audit Ledger Into Execution"
> — backend). This document covers only the frontend test tier + customer wiring
> and does NOT modify `scos/` or the approval contract. The two 6.7 efforts should
> be reconciled by the operator before a single commit.

## Verification Evidence (real runs)

### Frontend test tier
- `cd apps/control-center && pnpm install` (dev-only: vitest ^2.1.8,
  @testing-library/react ^16.1.0, @testing-library/jest-dom ^6.6.3, jsdom ^25.0.1)
  -> INSTALL_EXIT=0. esbuild build approved via `pnpm-workspace.yaml` (pnpm 11
  requireent); postinstall ran.
- `pnpm test` -> **12 passed (3 files)**, TEST_EXIT=0
    - tests/nav-wiring.test.tsx ............ 4 passed
    - tests/command-draft-panel.test.tsx ... 4 passed
    - tests/operator-approval-panel.test.tsx 4 passed (1 extra pending-state test)
- `pnpm lint` -> clean, LINT_EXIT=0
- `pnpm build` -> success, BUILD_EXIT=0 (4 static routes compiled)

### Customer error-report wiring (api_handler.py + customer.html)
- Customer e2e (live HTTPServer, 10 behaviors): 9 explicit PASS + malformed-JSON
  handled leniently (no 500 / no crash). All safe paths verified:
    - POST /api/report-error -> 201 (with payload)
    - POST /api/report-error -> 201 (empty body, lenient)
    - unknown route -> 404
    - malformed JSON body -> accepted leniently (no 500)
    - api_errors.log written
    - GET /error-report -> 200 and shows "尚未处理"
    - GET / -> 200 and customer.html contains `submitReport()` + `/api/report-error` fetch

## Scope Boundary
- Files added/modified (this stage):
    - apps/control-center/vitest.config.ts (NEW)
    - apps/control-center/tests/setup.ts (NEW)
    - apps/control-center/tests/nav-wiring.test.tsx (NEW)
    - apps/control-center/tests/command-draft-panel.test.tsx (NEW)
    - apps/control-center/tests/operator-approval-panel.test.tsx (NEW)
    - apps/control-center/package.json (MOD: test script + 4 devDeps)
    - apps/control-center/pnpm-lock.yaml (MOD: lockfile for new devDeps)
    - apps/control-center/pnpm-workspace.yaml (MOD: allowBuilds.esbuild=true)
    - apps/control-center/eslint.config.mjs (MOD: ignore tests/** + vitest.config.ts)
    - apps/control-center/README.md (MOD: Stage 6.7 section)
    - .gitignore (MOD: ignore .pytest_cache / coverage / test-results)
    - api_handler.py (NEW: report-error endpoint + error-report page)
    - customer.html (MOD: submitReport() wiring)
- UNTOUCHED by this stage (pre-existing, in-flight, NOT included):
    - docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md
    - scos/control_center/command_runner.py
    - scos/control_center/operator_approval.py
  These carry 159 insertions from a separate 6.7 effort; they are out of scope
  for the frontend test tier and must be committed separately or reconciled.

## Security / hygiene
- No secrets, API keys, tokens, or absolute private paths introduced.
- Frontend tests import ONLY frontend components + `lib/` types/data; they never
  import `scos/control_center` (grep-verified: none).
- No new API route types beyond the required `POST /api/report-error`; no network
  egress; no backend contract change.

## Risks / notes for operator
1. Two separate 6.7 efforts both use `Stage-6.7-plan.md`. This cert is filed as
   `Stage-6.7-frontend-test-tier.md` to avoid clobbering the backend one.
2. `pacesuper-creator-os` (stray text file in repo root) is unrelated garbage,
   not created by this stage — recommend the operator remove it separately.
3. pnpm v11 requires `allowBuilds.esbuild: true` in pnpm-workspace.yaml; this is a
   build-time tooling approval only, no runtime/backend impact.
