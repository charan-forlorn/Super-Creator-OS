# Stage 6 Execution Plan

## 1. Executive Summary

Stage 6 turns the Stage 5.1-5.9 local AI Command Center foundation (command
bridge, work sessions, adapter contracts, prompt/result packets, operator
review, cross-agent routing, result intake, git approval, operator runbooks)
into a **real, running local system**. Stage 5 deliberately shipped
mock-only, design-first artifacts; Stage 6 delivers the local backend/state
integration those artifacts were designed for — a local process that executes
the Stage 5.1 command bridge, persists Stage 5.2-5.9 state durably, and
streams events to the Control Center UI. Stage 6 stays strictly local-first
and approval-first: no cloud hosting, no SaaS surface, no payment/billing/CRM,
and no real AI dispatch without an explicit operator-approval gate.

Stage 6 is organized as exactly 10 focused work items (6.1-6.10), taken
directly from `docs/roadmap/STAGE6_HANDOFF.md`, with Stage 6.1 (defect
verification + Stage 5.10 gate re-run) as a hard prerequisite and Stage 6.10
as the final deterministic release/closure gate mirroring Stage 4.19 /
Stage 5.10.

This document is a Stage 6.0 planning artifact. It authorizes no
implementation by itself; each Stage 6.x work item requires its own approved
task before code changes begin.

## 2. Source of Truth

- `docs/roadmap/STAGE6_HANDOFF.md` — primary source of truth for Stage 6
  objective, stage list, non-goals, defects carried forward, risks, and
  acceptance criteria.
- `docs/certification/Stage-5-final-ai-command-center-certification.md` —
  Stage 5 closure record (gate GO, readiness 100/100, `stage_closed = True`,
  zero blockers) and remediation record for the Stage 5.6 defects.
- `docs/roadmap/STAGE5_HANDOFF.md` — still-open Stage 4→5 handoff items
  `stage5-001`..`stage5-010` and Gates 5.A-5.E, which Stage 6 items absorb.
- `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md` — binding
  three-layer architecture boundary Stage 6 must operate within.
- `docs/roadmap/STAGE6_HANDOFF_REVIEW.md` — Stage 6.0 interpretation notes,
  including resolution of the handoff-vs-certification defect-status conflict.

## 3. Stage 5 Handoff Summary

Stage 5 delivered (all local-first, mock/design-only, approval-first):

| Stage | Delivered |
|---|---|
| 5.1 | Local command bridge: draft → validate → operator approval → JSONL queue → allowlisted local runner → JSONL event log |
| 5.2 | AI work session manager: runtime registry, session lifecycle, JSONL session store |
| 5.3 | AI agent adapter contract layer: per-agent contract adapters, registry, simulator (no real dispatch) |
| 5.4 | Unified prompt/result packet models, builder, JSONL store |
| 5.5 | Operator packet review & manual handoff flow |
| 5.6 | Cross-agent workflow router: routing rules, route planning, JSONL route store (defects since remediated) |
| 5.7 | AI result intake & status update loop, project state updates, next-action decisions |
| 5.8 | Git commit/push approval gate: evidence snapshots, proposals, decisions — never runs real git |
| 5.9 | Local operator execution console / manual command runbook — never executes anything itself |
| 5.10 | Final AI command center certification gate (deterministic, re-runnable) |

Handed forward to Stage 6:

- The 10 recommended Stage 6 stages (see Section 7).
- Defect list from the handoff's "Known defects carried forward" section.
  **Interpretation note:** the Stage 5 final certification document records
  these Stage 5.6 defects as already remediated (gate GO, zero blockers).
  Stage 6.1 is therefore scoped as *verification/re-certification* of those
  fixes on the current committed tree — see `STAGE6_HANDOFF_REVIEW.md`.
- Still-open Stage 4→5 items `stage5-001`..`stage5-010` and Gates 5.A-5.E
  (command API, event stream, approval workflow, security upgrades,
  productization, monitoring, integration boundary), which map into
  Stage 6.2-6.9.

## 4. Stage 6 Objective

Turn the Stage 5 contracts and mock flows into a practical local execution
layer:

1. A real **local Control Center backend & command API** executing the
   Stage 5.1 command bridge (Stage 6.2).
2. **Durable local state** — SQLite WAL-backed store where JSONL append-only
   stores are insufficient for durability/concurrency (Stage 6.3).
3. A real **operator event stream** syncing backend state to the Control
   Center UI (Stage 6.4).
4. A deliberate, approval-gated **adapter runtime activation strategy**
   (Stage 6.5).
5. **Approval persistence and audit trail hardening** (Stage 6.6).
6. Supporting quality infrastructure: automated frontend tests (6.7),
   security scan coverage (6.8), monitoring/observability (6.9), and a final
   deterministic closure gate (6.10).

## 5. Stage 6 Non-Goals

Directly from the handoff, plus Stage 6.0 clarifications:

- No cloud hosting, SaaS multi-tenant surface, customer portal, or
  payment/billing/CRM integration — out of scope unless a later,
  separately-approved stage defines one.
- No retroactive Stage 5.11+ work; Stage 5 is closed at 5.10. Anything
  "should have been Stage 5" is Stage 6 backlog.
- No reopening or expanding Stage 4; Stage 4.1-4.19 public contracts stay
  intact.
- No real AI dispatch without an explicit, tested operator-approval gate in
  front of it.
- No bypassing local-first: Stage 6's backend is a local server/process on
  the operator's machine, never a hosted one.
- No autonomous outward-facing actions (send/spend/customer-facing) —
  operator approval is permanent.
- No Stage 6.x.y sub-fragmentation except blocker patches (see Section 8).

## 6. Architecture Boundary

Stage 6 operates entirely within the Operator Tools Layer (Layer 3) of the
SCOS Architecture Boundary Constitution:

- **Runtime Product Layer (`scos/` excluding `scos/control_center/`)** —
  untouched by Stage 6 except through explicit, versioned contracts. No
  Stage 6 code is imported by the product runtime.
- **Development Framework Layer (`.claude/`, `development/`, `skills/`,
  `scripts/`, `integrations/`, …)** — never imported into the operator
  runtime path. Stage 6.8 extends `scripts/security_scan_baseline.py`
  (a Layer 2 dev script) to *scan* Layer 3, which is read-only introspection
  and allowed.
- **Operator Tools Layer (`scos/control_center/`, `apps/control-center/`)** —
  where all Stage 6 implementation lives. Coupling to the other layers is via
  documented contracts (`docs/specification/*_CONTRACT.md`) only.

The full Stage 6 boundary is specified in
`docs/specification/STAGE6_SCOPE_BOUNDARY.md`.

## 7. Proposed Stage 6 Work Items

Exactly 10 items, mapped 1:1 from the handoff's recommended stage list.

### Stage 6.1 — Stage 5.6 defect verification & Stage 5.10 gate re-confirmation

- **Goal:** Verify the six remediated Stage 5.6 defects (package export gap,
  duplicate `ALLOWED_COMMAND_TYPES` lazy-export key, frontend wiring gap,
  README stray line, docstring gap, test invocation inconsistency) are fixed
  in the committed tree, then re-run the Stage 5.10 gate and confirm `GO`
  with zero error/critical blockers on a clean tree. If any defect is found
  unfixed at HEAD, fix it here as an isolated patch (this is the handoff's
  original Stage 6.1 scope).
- **Allowed files/scope:** read-only gate run; patch scope limited to
  `scos/control_center/__init__.py`, the three Stage 5.6 modules and tests,
  `apps/control-center/` Stage 5.6 wiring/README — only if a defect is
  actually present at HEAD.
- **Non-goals:** no new features; no Stage 5 expansion; no gate-rule changes.
- **Acceptance criteria:** Stage 5.10 gate returns `GO`, `accepted = True`,
  zero error/critical blockers, on a clean committed tree; evidence recorded
  in a Stage 6.1 certification doc.
- **Risk level:** Low. **Dependency:** none (entry point).
- **Owner agent:** Codex (verification) / Claude Code (patch if needed).
- **Prompt type:** review / regression-guard.

### Stage 6.2 — Local Control Center backend & command API

- **Goal:** Implement the Stage 5.1 command bridge as a real local execution
  surface: a local process exposing the typed command API (validate →
  approve → queue → run allowlisted local commands → log events), per
  `CONTROL_CENTER_COMMAND_API_DESIGN.md` and the Stage 5.1 contracts.
- **Allowed files/scope:** `scos/control_center/` (new backend modules),
  `apps/control-center/` (client wiring), new
  `docs/specification/*_CONTRACT.md` updates/additions, tests.
- **Non-goals:** no hosted server, no auth-for-remote-users, no real AI
  dispatch, no bypass of command validation or operator approval.
- **Acceptance criteria:** every command flows draft → validate → operator
  approval → queue → allowlisted runner → event log with no bypass path;
  contract tests green; runs entirely on localhost.
- **Risk level:** High (first real backend; boundary change from mock-only).
- **Dependency:** 6.1.
- **Owner agent:** Claude Code. **Prompt type:** implementation.

### Stage 6.3 — SQLite WAL-backed local store

- **Goal:** Replace JSONL append-only stores with a SQLite (WAL mode) local
  store where durability/concurrency requires it (sessions, packets,
  decisions, approvals), with deterministic migration from existing JSONL
  data and preservation of append-only audit semantics.
- **Allowed files/scope:** `scos/control_center/` store modules, migration
  utilities, tests; persistence contract doc.
- **Non-goals:** no external/hosted database, no ORM framework adoption
  decision beyond stdlib `sqlite3` unless separately approved, no schema for
  future SaaS features.
- **Acceptance criteria:** all Stage 5 state types persist and reload
  round-trip; JSONL→SQLite migration is deterministic and evidenced; audit
  records are never destructively updated.
- **Risk level:** Medium. **Dependency:** 6.2.
- **Owner agent:** Claude Code. **Prompt type:** implementation.

### Stage 6.4 — Real operator event stream / Control Center UI sync

- **Goal:** Stream backend events (command progress, state changes) to the
  Control Center UI from the append-only event log — deterministic and
  replayable first, transport second. Transport choice (localhost
  WebSocket/SSE/long-poll) is decided inside this stage and documented.
- **Allowed files/scope:** `scos/control_center/` event modules,
  `apps/control-center/` UI sync, event log contract doc, tests.
- **Non-goals:** no cross-machine transport, no third-party pub/sub, no
  events that trigger actions without operator approval.
- **Acceptance criteria:** UI reflects backend state end-to-end for at least
  one real command (closes the Gate 5.B intent); replay from the persisted
  log reproduces UI state deterministically.
- **Risk level:** Medium. **Dependency:** 6.2 (6.3 preferred first).
- **Owner agent:** Claude Code. **Prompt type:** implementation.

### Stage 6.5 — Adapter runtime activation strategy

- **Goal:** Decide which agent adapters (if any) become real dispatchers and
  implement only the approved subset — always behind the explicit
  operator-approval gate, always with the Stage 5.5 manual handoff flow
  preserved as fallback.
- **Allowed files/scope:** an activation-strategy decision document first;
  then `scos/control_center/` adapter runtime changes for approved adapters
  only; tests.
- **Non-goals:** no direct push of work to any AI agent without a recorded
  operator approval; no removal of the simulator or manual handoff path; no
  API-key/secret handling design beyond local operator-owned storage.
- **Acceptance criteria:** written activation decision approved by the
  operator before any dispatch code; every real dispatch is preceded by a
  persisted approval record; manual fallback demonstrably still works.
- **Risk level:** High (highest-risk workstream per the handoff).
- **Dependency:** 6.2, 6.6.
- **Owner agent:** ChatGPT (strategy/architecture) → Claude Code
  (implementation). **Prompt type:** architecture then implementation.

### Stage 6.6 — Operator approval persistence & audit trail hardening

- **Goal:** Persist every approve/deny decision durably (pending →
  approved/denied lifecycle) with a tamper-evident, append-only audit trail
  spanning commands, packets, git proposals, and (later) adapter dispatches.
- **Allowed files/scope:** `scos/control_center/` approval/audit modules,
  approval gate contract doc, tests.
- **Non-goals:** no delegated/automatic approval, no approval expiry
  automation that grants by default, no remote approval surface.
- **Acceptance criteria:** no approvable action executes without a persisted
  decision record; audit trail survives process restart; denial paths tested.
- **Risk level:** Medium. **Dependency:** 6.3 (durable store).
- **Owner agent:** Claude Code. **Prompt type:** implementation.

### Stage 6.7 — Automated test tier for `apps/control-center`

- **Goal:** Add a real test runner to the frontend (today only
  `dev`/`build`/`start`/`lint` exist) and a baseline suite covering the
  Stage 5 panels and new Stage 6 UI sync.
- **Allowed files/scope:** `apps/control-center/` test config, package
  scripts and dev-dependencies, test files; docs.
- **Non-goals:** no CI/cloud test infrastructure; no E2E browser automation
  requiring network services; no rewrite of existing components to be
  "testable".
- **Acceptance criteria:** `pnpm test` (or equivalent documented script)
  runs locally and green; baseline coverage over nav wiring and at least
  the command/approval panels; wired into the Stage 6.10 gate.
- **Risk level:** Low. **Dependency:** 6.4 (test what exists).
- **Owner agent:** Claude Code / Codex. **Prompt type:** tests.

### Stage 6.8 — Security hardening pass

- **Goal:** Extend `scripts/security_scan_baseline.py` coverage to
  `scos/control_center` and `apps/control-center`, and remediate findings.
- **Allowed files/scope:** `scripts/security_scan_baseline.py`, scanned
  targets for remediation only, security docs.
- **Non-goals:** no new external scanning services; no weakening of existing
  scan rules to pass; no scope creep into `scos/` runtime modules beyond
  findings remediation.
- **Acceptance criteria:** scan runs clean (or with documented accepted
  findings) over both new targets; wired into the Stage 6.10 gate.
- **Risk level:** Low-Medium. **Dependency:** 6.2 (scan the real backend).
- **Owner agent:** Codex. **Prompt type:** static scan / review.

### Stage 6.9 — Monitoring & observability

- **Goal:** Local health checks, structured logs/metrics, and drift detection
  for the live Control Center backend; a maintenance log convention under
  `docs/certification/`.
- **Allowed files/scope:** `scos/control_center/` health/metrics modules,
  operator docs, tests.
- **Non-goals:** no hosted telemetry/APM, no data leaving the machine, no
  background daemons beyond the backend process itself.
- **Acceptance criteria:** operator can determine backend health and recent
  activity deterministically from local artifacts; checks are re-runnable
  and offline-safe.
- **Risk level:** Low. **Dependency:** 6.2-6.4 live.
- **Owner agent:** Hermes (audit design) / Claude Code (implementation).
- **Prompt type:** workflow audit then implementation.

### Stage 6.10 — Stage 6 final release/closure gate

- **Goal:** A deterministic, re-runnable Stage 6 certification gate mirroring
  the Stage 4.19 / Stage 5.10 pattern: enumerated checks over 6.1-6.9
  deliverables, safety boundaries, git state, docs, tests, and security
  scans; produces GO/NO_GO, readiness score, blockers, and the Stage 7
  handoff.
- **Allowed files/scope:** `scos/control_center/` gate module + tests,
  `docs/certification/` gate report and closure doc,
  `docs/roadmap/STAGE7_HANDOFF.md`.
- **Non-goals:** no new features; no relaxation of prior gates; no Stage 7
  implementation.
- **Acceptance criteria:** gate returns `GO`, `accepted = True`,
  `stage_closed = True`, zero error/critical blockers; includes an
  over-fragmentation scan rejecting Stage 6.11+ markers.
- **Risk level:** Low. **Dependency:** 6.1-6.9 closed.
- **Owner agent:** ChatGPT (certification review) / Hermes (evidence review).
- **Prompt type:** certification.

## 8. Recommended Stage Sequence

```
6.1  (hard prerequisite — verify defects fixed, gate GO)
 └─ 6.2  (local backend & command API)
     └─ 6.3  (SQLite WAL store)
         ├─ 6.4  (event stream / UI sync)
         └─ 6.6  (approval persistence & audit)
              └─ 6.5  (adapter activation — only after 6.6 audit exists)
 6.7, 6.8  (parallelizable once 6.2/6.4 exist)
 6.9  (after backend is live)
 6.10 (final gate — last)
```

Sequencing rules:

- 6.1 must complete before any other Stage 6 item starts (handoff: "a hard
  prerequisite, not optional cleanup").
- 6.5 (real dispatch decision) must not start before 6.6 (approval
  persistence/audit) is closed.
- 6.10 runs only when 6.1-6.9 all pass their acceptance criteria.
- Patch stages (6.x fix-ups) are allowed only for a blocker, build failure,
  deploy failure, certification failure, or demonstrably wrong decision
  data — never for feature additions. No 6.1.1/6.1.2-style fragmentation
  otherwise.

## 9. Stage 6.1 Recommended First Task

**Stage 6.1 — Stage 5.6 defect verification & Stage 5.10 gate
re-confirmation.**

Concretely: on the current committed tree (`4ce48a1`), verify each of the six
Stage 5.6 defects the handoff carries forward is actually fixed at HEAD (the
Stage 5 final certification records them as remediated); re-run
`run_stage5_final_certification` with a fresh `checked_at`; confirm `GO`,
`accepted = True`, zero error/critical blockers, readiness 100/100 on a clean
tree; record the evidence in `docs/certification/Stage-6.1-plan.md`. Only if
a defect is found unfixed does 6.1 expand to the isolated patch the handoff
originally scoped.

This is the cheapest possible first stage, de-risks everything downstream,
and satisfies the handoff's first acceptance criterion verbatim.

## 10. Acceptance Criteria

Summarized here; the normative version is
`docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md`.

- Stage 6.1 lands and a Stage 5.10 gate re-run returns `GO` with zero
  error/critical blockers.
- The Stage 6.2 backend never bypasses Stage 5.1 command validation /
  operator approval.
- Every Stage 6.x item meets its per-item acceptance criteria (Section 7)
  with deterministic evidence artifacts under `docs/certification/`.
- Stage 6.10's gate exists, enumerates its own deterministic checks, and
  returns `GO` / `accepted = True` / `stage_closed = True` before Stage 6 is
  considered closed.
- Stage 4 and Stage 5 regression behavior remains intact (their gates still
  return GO when re-run).

## 11. Testing Strategy

- **Tier 1 — module tests:** every new `scos/control_center/` module ships
  with the same direct-run test convention Stage 5 established (sys.path
  bootstrap + `if __name__ == "__main__"` runner).
- **Tier 2 — contract tests:** command API request/response envelopes, event
  log schema, approval lifecycle, and persistence round-trips tested against
  the `docs/specification/*_CONTRACT.md` documents.
- **Tier 3 — frontend tests:** the Stage 6.7 runner covers panel wiring and
  UI sync; `pnpm lint` / `pnpm build` remain required-when-available.
- **Tier 4 — gate tests:** Stage 6.10 gate has its own test file and is
  itself deterministic and re-runnable offline.
- Existing smoke/security scripts (`scripts/test_smoke.py`,
  `scripts/security_scan_baseline.py`) stay green throughout.
- All tests run locally, offline, with no network and no real AI dispatch.

## 12. Security / Safety Rules

- Operator approval is the safety boundary: no command execution, git
  action, or AI dispatch without a persisted approve decision.
- The command runner allowlist is the only execution surface; no arbitrary
  shell passthrough.
- The backend binds to localhost only; no remote listener, no auth tokens
  minted for remote parties.
- Secrets (if any adapter is activated in 6.5) stay in local operator-owned
  storage, never committed, never logged.
- `scripts/security_scan_baseline.py` (extended in 6.8) must pass before
  Stage 6.10.
- The Stage 5.8 rule stands: proposal/decision artifacts, never
  auto-executed git commands, outside explicitly approved runs.

## 13. Local-First Constraints

- All Stage 6 processes run on the operator's machine; no cloud hosting,
  hosted databases, or third-party runtime services.
- All persistence is local files (JSONL and SQLite under the repo/workspace
  data directories).
- All checks and gates are runnable offline and deterministically.
- Network access, if any stage needs it (6.5 real dispatch), is
  per-dispatch, operator-approved, and never a standing background
  connection.

## 14. Operator Approval Rules

- Pending → approved/denied lifecycle for every approvable action; decisions
  are persisted (6.6) and auditable.
- No default-approve, no auto-approve timers, no batch blanket approvals for
  outward-facing actions.
- Manual fallback (Stage 5.5 manual handoff packages, Stage 5.9 runbooks)
  remains available for every AI-related workflow even after 6.5.
- Denials are terminal for that action instance; re-submission creates a new
  auditable record.

## 15. Risk Register

| # | Risk | Level | Mitigation |
|---|---|---|---|
| R1 | Building 6.2+ on unverified Stage 5.6 fixes bakes latent defects into the real backend | High | 6.1 is a hard prerequisite; gate re-run must return GO first |
| R2 | Real backend/API/database is a major boundary change from Stage 5's mock-only design | High | Stage 6 defines its own explicit boundary (`STAGE6_SCOPE_BOUNDARY.md`) rather than inheriting Stage 5's |
| R3 | Real AI dispatch (6.5) bypassing or weakening the approval gate | High | 6.5 blocked on 6.6; written activation decision required; approval record precedes every dispatch; manual fallback preserved |
| R4 | JSONL→SQLite migration corrupting or losing Stage 5 state | Medium | Deterministic migration with round-trip tests and evidence; JSONL retained as source until verified |
| R5 | Event transport choice (WebSocket/SSE/polling) leaking beyond localhost or becoming a hidden background worker | Medium | Localhost-only binding rule; replayable log is primary, transport secondary |
| R6 | Scope creep toward SaaS/cloud/payment surfaces | Medium | Explicit non-goals + 6.10 gate scans; commercial gate required for any such work |
| R7 | Frontend remains untested while backend integration grows | Medium | 6.7 adds the test tier before 6.10 certifies |
| R8 | Handoff-vs-certification defect-status ambiguity causes duplicate or skipped work | Low | Resolved in `STAGE6_HANDOFF_REVIEW.md`: 6.1 verifies rather than re-fixes |
| R9 | Stage over-fragmentation (6.x.y patches multiplying) | Low | Patch-only-for-blockers rule; 6.10 over-fragmentation scan |

Current blockers: **none** (Stage 5 closed at GO 100/100; preflight clean).

## 16. Stage 6 Close Criteria

Stage 6 is closed only when all of the following hold:

1. Stages 6.1-6.9 each meet their acceptance criteria with evidence docs
   under `docs/certification/`.
2. The Stage 6.10 gate returns `GO`, `accepted = True`,
   `stage_closed = True`, zero error/critical blockers.
3. Stage 4.19 and Stage 5.10 gates still return GO (no regression).
4. Working tree clean, HEAD == origin/main at certification time.
5. `docs/roadmap/STAGE7_HANDOFF.md` exists with the Stage 7 handoff.
6. No Stage 6.11+ markers exist anywhere in the repo.

## 17. Stage 7 Handoff Draft

To be finalized by Stage 6.10; expected shape:

- **Theme candidates:** productized customer workflow execution on top of the
  live Control Center (absorbing the still-open Gate 5.D intent), and/or the
  first separately-approved external-integration stage (real outward
  channels behind the approval gate).
- **Carried forward:** any Stage 4→5 items (`stage5-001`..`stage5-010`,
  Gates 5.A-5.E) not fully absorbed by Stage 6.2-6.9 — expected residue:
  security upgrades beyond scan coverage (SBOM, provenance, signing) and
  customer-workflow productization.
- **Boundary:** cloud/SaaS/payment/CRM remain out of scope until a dedicated
  commercial gate authorizes them.
- **Rule:** Stage 6 closes at 6.10; anything "should have been Stage 6" is
  Stage 7 backlog.

## 18. Would-be Commit Message

```
docs(roadmap): add Stage 6.0 execution plan, scope boundary, and acceptance criteria

Stage 6.0 — Stage 6 Handoff Review & Execution Plan (planning only, no
runtime changes):

- docs/roadmap/STAGE6_EXECUTION_PLAN.md: 10 work items (6.1-6.10), sequence,
  risks, close criteria, Stage 7 handoff draft
- docs/specification/STAGE6_SCOPE_BOUNDARY.md: allowed/forbidden scope and
  layer boundaries
- docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md: entry/per-stage/final
  criteria and close gate
- docs/certification/Stage-6.0-plan.md: Stage 6.0 certification record
- docs/roadmap/STAGE6_HANDOFF_REVIEW.md: handoff item mapping and
  defect-status conflict resolution (6.1 = verify, not re-fix)

Stage 4 and Stage 5 remain closed; no implementation authorized until
Stage 6.1 is approved.
```
