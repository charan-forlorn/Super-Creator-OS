# Stage 8.0 Plan - Stage 8 Planning, Scope Boundary, and Acceptance Criteria

Predecessor Stage 7 closure commit:
`d5129daf0b97626b42703dd2b8c5e2b8e0fa10f9`
(`fix(control-center): calibrate Stage 7.8 closure gate scoring`).

## Objective

Define the Stage 8 execution plan, scope boundary, acceptance criteria, risk
model, and recommended Stage 8.1 starting point.

Stage 8.0 answers:

```text
What should Stage 8 build next, in what order, with what constraints, and what
is the correct Stage 8.1 implementation starting point?
```

## Scope

Allowed files created:

- `docs/roadmap/STAGE8_HANDOFF_REVIEW.md`
- `docs/roadmap/STAGE8_EXECUTION_PLAN.md`
- `docs/specification/STAGE8_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md`
- `docs/certification/Stage-8.0-plan.md`

Stage 8.0 is planning and governance only.

## Non-Goals

- no Stage 8.1 implementation
- no live transport
- no WebSocket, SSE/EventSource, polling, timers, or background workers
- no backend routes or Next.js API routes
- no frontend feature
- no runtime behavior change
- no database schema change or migration
- no real ChatGPT, Claude Code, Codex, Hermes, or other AI dispatch
- no adapter activation
- no API-key handling, secret storage, or external API call
- no Buffer integration
- no cloud, SaaS, payment, CRM, customer portal, or external publishing
  behavior
- no package or dependency change
- no Stage 4, Stage 5, Stage 6, or Stage 7 public contract break
- no commit, push, tag, or release

## Files Created

- `docs/roadmap/STAGE8_HANDOFF_REVIEW.md`
- `docs/roadmap/STAGE8_EXECUTION_PLAN.md`
- `docs/specification/STAGE8_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md`
- `docs/certification/Stage-8.0-plan.md`

## Evidence Reviewed

- `docs/roadmap/STAGE8_HANDOFF.md`
- `docs/certification/Stage-7-final-closure.md`
- `docs/certification/Stage-7.8-plan.md`
- `docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md`
- `docs/roadmap/STAGE7_EXECUTION_PLAN.md`
- `docs/specification/STAGE7_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE7_ACCEPTANCE_CRITERIA.md`
- `docs/roadmap/STAGE7_HANDOFF_REVIEW.md`
- `docs/certification/Stage-6-final-integration-release.md`
- `docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md`
- `docs/roadmap/STAGE6_HANDOFF.md`
- `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`
- `CLAUDE.md`

## Tests and Checks Run

Required after docs are written:

```text
git status --short --untracked-files=all
git diff --stat
git diff --name-only
```

Optional local checks when available:

```text
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
```

No frontend checks are required because Stage 8.0 must not touch frontend
files.

## Risks

- Stage 8 could treat transport decision work as transport implementation
  approval.
- Stage 8 could treat adapter preflight as real adapter activation approval.
- Stage 8 could introduce API-key handling before a credential policy exists.
- Stage 8 could expand into cloud, SaaS, payment, CRM, customer portal,
  Buffer, or external API behavior without an explicit stage boundary.
- Stage 8 could weaken Stage 4, Stage 5, Stage 6, or Stage 7 public
  contracts.

## Decision Log

| Decision | Status | Rationale |
|---|---|---|
| Stage 8 theme is Controlled Local Integration Activation & Operator Runtime Readiness | Approved for Stage 8 planning | Matches Stage 8 handoff and preserves local-first scope. |
| Stage 8.1 should be Local Transport Activation Decision & Safety Contract | Recommended | Transport is the first risky runtime boundary and must be decided before implementation. |
| Live transport implementation | Proposed but not yet approved | Requires Stage 8.1 decision first. |
| Real adapter activation | Forbidden until explicit operator approval | Stage 7.7 was preflight-only. |
| API-key and secret handling implementation | Forbidden until explicit operator approval | Stage 8.3 must define policy before use. |
| Cloud/SaaS/payment/CRM/customer portal, Buffer, and external integrations | Deferred and forbidden until explicit operator approval | Outside local-first Stage 8 readiness scope. |

## Stage 8.1 Recommendation

Stage 8.1 should be **Local Transport Activation Decision & Safety Contract**.
It should compare no transport, file snapshot refresh, local HTTP, WebSocket,
SSE/EventSource, and polling. It should decide whether a later Stage 8 item
may implement one local-only transport option. It should not implement
transport itself.

## PASS Criteria

Stage 8.0 passes only if:

- preflight passes on `main` with `HEAD == origin/main`
- the working tree starts clean
- only the five Stage 8.0 docs are created
- no existing runtime files are modified
- no `scos/` files are modified
- no `apps/control-center/` files are modified
- no package or dependency files are modified
- Stage 8 mission, scope boundary, acceptance criteria, handoff review, and
  Stage 8.1 recommendation are documented
- transport remains unimplemented
- real adapter activation remains unimplemented
- API-key and secret handling remain unimplemented
- cloud/SaaS/payment/CRM/customer portal, Buffer, and external integrations
  remain forbidden unless a later explicit stage changes the boundary
- no Stage 8.1 code or runtime behavior is implemented
- no commit, push, tag, or release is performed
- final report includes git status and diff evidence

## Would-Be Commit Message

```text
docs(roadmap): add Stage 8.0 execution plan, scope boundary, and acceptance criteria
```
