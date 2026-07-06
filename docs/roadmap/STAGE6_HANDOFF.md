# Stage 6 Handoff

## Stage 6 objective

Turn the Stage 5.1-5.9 local AI Command Center foundation (command bridge,
work sessions, adapter contracts, prompt/result packets, operator review,
cross-agent routing, result intake, git approval, operator execution
runbooks) into a real, running local system - starting with the local
backend/state integration Stage 5 deliberately left undone, not with any
cloud/SaaS/payment surface.

## Recommended Stage 6 stage list

1. **Stage 6.1** - Fix the two confirmed Stage 5.6 defects (package export
   gap, duplicate lazy-export key) as a dedicated, isolated patch, then
   re-run the Stage 5.10 gate to confirm `GO`.
2. **Stage 6.2** - Local Control Center backend & command API (turn the
   Stage 5.1 command bridge design into a real local execution surface).
3. **Stage 6.3** - SQLite WAL-backed local store, replacing the JSONL
   append-only stores where durability/concurrency requires it.
4. **Stage 6.4** - Real operator event stream / Control Center UI sync.
5. **Stage 6.5** - Adapter runtime activation strategy: decide which agent
   adapters (if any) become real dispatchers, always behind explicit
   operator approval.
6. **Stage 6.6** - Operator approval persistence and audit trail hardening.
7. **Stage 6.7** - Automated test tier for `apps/control-center` (add a
   real test runner; today only `dev`/`build`/`start`/`lint` exist).
8. **Stage 6.8** - Security hardening pass extending
   `scripts/security_scan_baseline.py` coverage to `scos/control_center`
   and `apps/control-center`.
9. **Stage 6.9** - Monitoring and observability for the Control Center
   backend once it is live.
10. **Stage 6.10** - Stage 6 final release/closure gate, mirroring the
    Stage 4.19 / Stage 5.10 certification pattern.

## Explicit non-goals

- No cloud hosting, SaaS multi-tenant surface, or payment/billing/CRM
  integration in Stage 6 unless a later, separately-approved stage defines
  one.
- No retroactive Stage 5.11+ work - Stage 5 is closed at 5.10; anything
  discovered as "should have been Stage 5" becomes Stage 6 backlog instead.
- No real AI dispatch without an explicit operator-approval gate in front
  of it, preserving the Stage 5 approval-first boundary.
- No bypassing the local-first principle: Stage 6's first backend is a
  local server/process, not a hosted one.

## First Stage 6 candidate: local backend/state integration

The first concrete Stage 6 candidate is **local backend/state
integration** - a real local process that executes the Stage 5.1 command
bridge, persists Stage 5.2-5.9 state (sessions, packets, decisions,
approvals) durably, and streams events to the Control Center UI. This is
explicitly **not** a cloud deployment, not a SaaS product, and not a
payment/billing integration - those remain out of scope until a dedicated
future stage authorizes them.

## Known defects carried forward

- Stage 5.6 package export gap (`scos/control_center/__init__.py` has zero
  `workflow_router*` exports).
- Duplicate `ALLOWED_COMMAND_TYPES` lazy-export key (Stage 5.9 silently
  shadows Stage 5.1's constant).
- Stage 5.6 frontend wiring gap (`workflow-router-panel.tsx` never rendered).
- Stage 5.6 README stray leftover line.
- Stage 5.6 module docstring convention gap (3 files, no
  `"""SCOS Stage 5.6 ..."""` header).
- Stage 5.6 test invocation inconsistency (different import bootstrap than
  every other stage's test file).
- Still-open Stage 4->5 handoff items `stage5-001`..`stage5-010` from the
  Stage 4.19 gate report and Gates 5.A-5.E from `STAGE5_HANDOFF.md`
  (unmodified by this stage).

## Risks

- Building Stage 6.2+ on top of the unfixed Stage 5.6 defects would bake a
  silent constant-shadowing bug and a dead frontend panel into the real
  backend; Stage 6.1 (fixing them first) is a hard prerequisite, not
  optional cleanup.
- Introducing a real backend/API/database is a significant boundary change
  from Stage 5's local-only, mock-only design; Stage 6 must define its own
  safety boundary explicitly rather than inheriting Stage 5's by default.
- Real AI dispatch (Stage 6.5) is the highest-risk workstream; it must not
  proceed without an explicit, tested operator-approval gate reused or
  extended from Stage 5.1's command bridge.

## Acceptance criteria

- Stage 6.1 lands and a re-run of the Stage 5.10 gate against the repo
  returns `GO` with zero error/critical blockers.
- Stage 6.2's backend never bypasses the Stage 5.1 command validation /
  operator approval flow.
- Stage 6's own final release gate (Stage 6.10) exists and enumerates its
  own deterministic checks, mirroring the Stage 4.19 / Stage 5.10 pattern,
  before Stage 6 is considered closed.
