# Stage 7.8 Plan - Stage 7 Closure Gate and Stage 8 Handoff

Predecessor: Stage 7.7, confirmed at commit
`01b81bc9317ab08b7c56131ffa1f655a84841af5`.

## Objective

Create the final deterministic Stage 7 closure gate and Stage 8 handoff
record. The stage certifies, closes, and hands off; it does not add product
features.

## Scope

Allowed backend files:

- `scos/control_center/stage7_closure_models.py`
- `scos/control_center/stage7_closure_gate.py`
- `scos/control_center/tests/test_stage7_closure_models.py`
- `scos/control_center/tests/test_stage7_closure_gate.py`
- Stage 7.8 lazy exports in `scos/control_center/__init__.py`

Allowed docs:

- `docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md`
- `docs/certification/Stage-7.8-plan.md`
- `docs/certification/Stage-7-final-closure.md`
- `docs/roadmap/STAGE8_HANDOFF.md`

## Non-Goals

- no Stage 7.9 feature work
- no frontend feature
- no live transport
- no WebSocket, SSE/EventSource, polling, timers, or background workers
- no real AI dispatch
- no real adapter activation
- no API-key flow
- no network, cloud, SaaS, payment, CRM, or customer portal behavior
- no command execution inside the closure gate
- no runtime store mutation
- no Certified Core, Stage 4, Stage 5, Stage 6, or Stage 7.1-7.7 contract break
- no dependency install
- no commit, push, tag, or release

## Test Plan

Run from repo root:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_stage7_closure_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_stage7_closure_gate.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Run from `apps/control-center` when scripts and dependencies are available:

```text
pnpm test
pnpm lint
pnpm build
```

Do not install dependencies during Stage 7.8.

## Acceptance Criteria

- Required git preflight passes.
- Closure models are immutable and deterministic.
- `checked_at` is caller-supplied and required.
- Stage 7.1-7.7 artifacts, docs, contracts, and tests are verified.
- Stage 4, Stage 5, and Stage 6 closure assumptions remain compatible.
- Required backend, smoke, security, release, and frontend checks pass or exact
  failure/skip evidence is documented.
- No implicit output report is written.
- Explicit output writes only inside `repo_root`.
- Optional runtime artifact gaps remain visible warnings but do not reduce the
  closure score when required evidence is complete.
- Stage 8 handoff exists and separates implemented, deferred, forbidden, and
  open-decision items.
- No forbidden Stage 7.8 behavior is introduced.

## Risks

- Optional runtime files may be absent on a clean checkout and should remain
  warnings only.
- Stage 8 planning could accidentally treat deferred transport or adapter
  activation as already approved.
- Closure evidence can drift if later commits alter Stage 7 contracts without
  updating the closure gate.

## Would-Be Commit Message

```text
docs(control-center): add Stage 7.8 closure gate and Stage 8 handoff
```
