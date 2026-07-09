# Stage 6.8 Certification Plan — Security Hardening Pass

## 1. Status

**IMPLEMENTED / READY FOR REVIEW**

- Scanner implementation is complete for the Stage 6.8 security hardening pass.
- No Stage 6.8 commit has been created.
- No push has been performed.

## 2. Objective

Stage 6.8 extends the local security scan baseline so it covers the Control
Center implementation surfaces:

- `scos/control_center`
- `apps/control-center`

The intent is to harden the existing local security gate before further
automation, transport, or integration work is allowed to proceed.

## 3. Scope

Allowed future implementation files:

- `scripts/security_scan_baseline.py`
- Scanner test file if needed
- `docs/certification/Stage-6.8-plan.md`

Possible future documentation only if justified:

- `docs/security/SECURITY_HARDENING_BASELINE.md`

## 4. Non-goals

Stage 6.8 must not include:

- No Buffer integration.
- No `integrations/buffer` commit.
- No Read API / State Query Surface.
- No backend API implementation.
- No WebSocket.
- No SSE.
- No polling.
- No cloud/network/SaaS behavior.
- No real AI dispatch.
- No payment/CRM/customer portal.
- No frontend runtime refactor.
- No `control_center` runtime behavior change.

## 5. Out-of-scope local work

The following local files are excluded from Stage 6.8:

- `IDEA.md`
- `docs/integrations/BUFFER_CONNECTOR.md`
- `integrations/buffer/`

These files must not be included in Stage 6.8 staging, commit, or push.

## 6. Scanner coverage targets

Stage 6.8 implementation must extend scanner coverage to:

- `scos/control_center`
- `apps/control-center`

## 7. Canonical rule source

`scripts/security_scan_baseline.py` must reuse, import, or safely mirror
canonical rule tables and scanner conventions from:

- `scos/control_center/stage5_final_certification.py`

Avoid divergent duplicate scanner rule sets.

## 8. Required rule categories

Future implementation must cover:

- Network libraries.
- Subprocess/shell.
- Real AI dispatch imports such as `openai` / `anthropic`.
- Frontend transport such as `fetch` / `XMLHttpRequest` / `axios`.
- WebSocket / EventSource / polling patterns.
- `Date.now` / `Math.random` / `crypto.randomUUID`.
- `localStorage` / `sessionStorage`.
- Secrets / token literals / committed `.env`.
- Destructive audit ledger SQL such as `DELETE FROM audit_ledger` or
  `UPDATE audit_ledger`.
- Remote bind / `0.0.0.0`.

## 9. False-positive protections

Scanner rules must avoid flagging:

- Comments/docstrings saying "no fetch", "no socket", "No WebSocket".
- Allowed subprocess usage in `command_runner.py`.
- Test-only monkeypatch references for random/time/datetime checks.

## 10. Expected acceptance criteria

Stage 6.8 passes when:

- `Stage-6.8-plan.md` exists.
- Scanner covers `scos/control_center`.
- Scanner covers `apps/control-center`.
- Scanner avoids duplicate rule drift where possible.
- Current committed tree scans clean.
- No `integrations/buffer` files are staged.
- No Buffer/API/network integration enters the Stage 6.8 commit.
- Tests/security scan pass.
- No commit/push happens without operator approval.

## 11. Test plan

Recommended commands for future implementation:

- `.venv\Scripts\python.exe scripts/security_scan_baseline.py`
- `.venv\Scripts\python.exe scripts/test_smoke.py`
- `.venv\Scripts\python.exe scripts/test_release.py`
- `.venv\Scripts\python.exe -m pytest scos/control_center/tests -q`
- `cd apps/control-center && pnpm test`
- `cd apps/control-center && pnpm lint`
- `cd apps/control-center && pnpm build`

## 12. Risks

- Accidental `git add -A` may include `integrations/buffer`.
- Scanner rule drift.
- False positives from comments/docstrings.
- Subprocess allowlist mistakes.
- Frontend mock strings triggering secret scan.
- Stage 6.8 scope creep into Buffer/API integration.

## 13. Implementation handoff

Stage 6.8 implementation modified `scripts/security_scan_baseline.py` only,
plus focused scanner tests under `scripts/tests/test_security_scan_baseline.py`.
No Control Center runtime module, frontend source file, Buffer integration, or
dependency manifest was modified.

## 14. Implementation summary

- Preserved existing Stage 4.18 scan behavior for `scos/commercial`, `scripts`,
  and root config files.
- Added backend scan coverage for `scos/control_center`.
- Added frontend scan coverage for `apps/control-center`.
- Frontend scanning is limited to `.ts`, `.tsx`, `.js`, and `.jsx`.
- Frontend scanning skips `node_modules`, `.next`, `.vercel`, `dist`, `build`,
  and `coverage`.
- Extended redacted secret/token scanning across the new roots.
- Added Control Center checks for network imports, real AI dispatch imports,
  browser/GUI/clipboard automation imports, subprocess/shell misuse, destructive
  `audit_ledger` SQL, and remote bind literals.
- Added frontend checks for transport, polling, nondeterministic browser APIs,
  storage APIs, server actions, clipboard automation, API routes, `route.ts`,
  and `middleware.ts`.

## 15. Files changed

- `scripts/security_scan_baseline.py`
- `scripts/tests/test_security_scan_baseline.py`
- `docs/certification/Stage-6.8-plan.md`

## 16. Rule sources reused or mirrored

The Stage 6.8 scanner safely mirrors the relevant scanner conventions from
`scos/control_center/stage5_final_certification.py` instead of importing the
certification gate directly. Direct import was avoided because the baseline
script must remain a standalone, local, deterministic scanner over its own
target tree and should not couple runtime scan behavior to the Stage 5
certification module's broader gate orchestration.

Mirrored conventions:

- Fragmented forbidden token literals so the scanner does not flag itself.
- Triple-quoted docstring stripping.
- Negated/comment policy-language filtering.
- Frontend static source scanning and `app/api` / `route.ts` / `middleware.ts`
  path checks.
- Subprocess allowlist discipline, with runtime exceptions for
  `command_runner.py`, `stage5_final_certification.py`, and the scanner itself.

## 17. Commands run and test results

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe scripts/security_scan_baseline.py` | PASS; 293 files scanned, 0 findings |
| `.venv\Scripts\python.exe -m pytest scripts\tests\test_security_scan_baseline.py -q --basetemp .pytest-tmp` | PASS; 3 passed, 0 failed; warning: default `.pytest_cache` write denied |
| `.venv\Scripts\python.exe scripts/test_smoke.py` | PASS; 16 passed, 0 failed |
| `.venv\Scripts\python.exe scripts/test_release.py` | PASS; 9 passed, 1 warned, 0 failed; warning was expected dirty Stage 6.8 worktree plus unreadable `.pytest_cache` paths |
| `.venv\Scripts\python.exe -m pytest scos\control_center\tests -q --basetemp .pytest-control-center-tmp` | PASS; 395 passed, 0 failed; warning: default `.pytest_cache` write denied |
| `pnpm test` | Initial PowerShell policy failure on `pnpm.ps1`; no tests executed |
| `pnpm lint` | Initial PowerShell policy failure on `pnpm.ps1`; no lint executed |
| `pnpm build` | Initial PowerShell policy failure on `pnpm.ps1`; no build executed |
| `pnpm.cmd test` | PASS; 3 frontend test files passed, 12 tests passed |
| `pnpm.cmd lint` | PASS |
| `pnpm.cmd build` | PASS; Next.js production build compiled successfully |

## 18. Findings

- Security scan findings: 0.
- Current committed tree scans clean under the expanded Stage 6.8 scope.
- No `integrations/buffer` files were scanned as visible Git status inputs,
  staged, modified, or included in Stage 6.8 changes.

## 19. False-positive notes

- Comments/docstrings and negated policy language such as "no fetch",
  "No WebSocket", and disabled future transport references are filtered.
- The scanner avoids bare substring matching for frontend transport terms.
- The scanner avoids the previous `pty` substring trap in words such as
  `_require_nonempty` by checking import/member-use shapes.
- Runtime subprocess checks exclude test fixture scaffolding while global
  token/secret scanning still covers test files.
- `command_runner.py`, `stage5_final_certification.py`, and
  `scripts/security_scan_baseline.py` are explicit subprocess allowlist entries.

## 20. Final verdict

**PASS**

Stage 6.8 security hardening is implemented and verified locally. No commit or
push has been performed.
