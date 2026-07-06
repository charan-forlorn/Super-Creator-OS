# Stage 6 Scope Boundary

Normative boundary specification for Stage 6 (Local Control Center Real
Integration). Subordinate to
`docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`; where this
document is silent, the constitution governs. Defined by Stage 6.0; binding
for Stages 6.1-6.10.

## 1. Stage 6 Allowed Scope

- Implementation inside the Operator Tools Layer only:
  `scos/control_center/` and `apps/control-center/`.
- A **local** Control Center backend process and command API (Stage 6.2),
  bound to localhost.
- Local persistence: JSONL stores and SQLite (WAL) files on the operator's
  machine (Stage 6.3).
- A local operator event stream and Control Center UI sync (Stage 6.4).
- Approval-gated adapter runtime activation, decided and documented before
  implementation (Stage 6.5).
- Approval persistence and audit trail hardening (Stage 6.6).
- Frontend test tooling for `apps/control-center` (Stage 6.7).
- Extension of `scripts/security_scan_baseline.py` coverage and remediation
  of its findings (Stage 6.8).
- Local monitoring/observability for the backend (Stage 6.9).
- The Stage 6.10 deterministic closure gate and its docs.
- New/updated contract documents under `docs/specification/` and
  certification evidence under `docs/certification/`.

## 2. Stage 6 Forbidden Scope

- Cloud hosting, hosted databases, SaaS multi-tenant surfaces, customer
  portals.
- Payment, billing, or CRM integration of any kind.
- Fully autonomous outward-facing actions (send, spend, publish,
  customer-facing) — all require explicit operator approval, permanently.
- Stage 5.11+ or Stage 4.20+ markers; reopening closed stages.
- Changes to Stage 4 or Stage 5 public contracts, except genuine defect
  fixes that preserve published contracts (Stage 6.1 scope only).
- Implementation changes to `scos/knowledge` or `scos/commercial`.
- Background daemons, timers, or polling loops beyond the explicit local
  backend process and its documented event transport.
- Browser/GUI/clipboard automation.
- Any network egress except per-dispatch, operator-approved calls under an
  activated Stage 6.5 adapter.

## 3. Runtime Product Layer Boundary

`scos/` (excluding `scos/control_center/`) is untouched by Stage 6.
Interaction is only via explicit, versioned contracts
(`docs/specification/*_CONTRACT.md`); the product runtime must never import
Stage 6 code, and Stage 6 code must never reach into runtime internals
directly.

## 4. Development Framework Layer Boundary

`.claude/`, `development/`, `skills/`, `integrations/`, `scripts/`,
`analysis/`, `project_audit/` are never imported into the operator runtime
path. Stage 6.8 modifies `scripts/security_scan_baseline.py` (a Layer 2
dev/test script) to *scan* Layer 3 — read-only introspection, which the
constitution allows. Nothing in Layer 2 becomes a runtime dependency of the
backend.

## 5. Operator Tools Layer Boundary

All Stage 6 implementation lives in `scos/control_center/` and
`apps/control-center/`. The layer coordinates between the product and the
development framework via documented contracts only — never direct
cross-layer imports. The AI Work Session Manager and everything built on it
stays in this coordination boundary and is never embedded into the product.

## 6. Control Center Boundary

- The UI (`apps/control-center/`) is an operator surface: it displays state,
  collects operator decisions, and submits typed commands. It never executes
  work itself.
- The UI talks only to the local backend's documented command/event API —
  no direct file mutation of backend stores, no direct AI calls.
- Every actionable UI control maps to a command that passes validation and
  the approval gate.

## 7. Local Backend Boundary

- One local process on the operator's machine; binds to localhost only.
- Exposes exactly the typed command API and event stream defined in the
  contracts; no arbitrary shell endpoint, no remote administration.
- Executes only allowlisted commands via the Stage 5.1 runner pattern;
  the allowlist is versioned and reviewed.
- May be started/stopped only by the operator; no auto-start services.

## 8. Persistence Boundary

- All state lives in local files: JSONL (append-only logs, audit) and SQLite
  WAL databases (durable/concurrent state) under repo/workspace data
  directories.
- Audit-bearing records are append-only; no destructive updates to decision
  or event history.
- JSONL→SQLite migration is deterministic, evidenced, and keeps JSONL as the
  source of truth until round-trip verification passes.
- No hosted or networked database, no external cache.

## 9. AI Adapter Boundary

- Adapters remain contract-shaped (Stage 5.3); the simulator and the manual
  handoff path (Stage 5.5) are never removed.
- No adapter performs real dispatch until Stage 6.5 produces a written,
  operator-approved activation decision for that specific adapter.
- Each real dispatch requires a persisted operator approval record created
  before the call; no standing "approve all" state.
- Credentials for activated adapters are local, operator-owned, never
  committed, never logged.

## 10. Security Boundary

- Localhost-only listeners; no remote auth surface.
- Allowlisted command execution only; command validation cannot be disabled
  or bypassed by any API path.
- `scripts/security_scan_baseline.py` (extended per Stage 6.8) must pass
  over `scos/control_center` and `apps/control-center` before Stage 6
  closes.
- Secrets never enter the repo, logs, event stream, or evidence artifacts.
- Git actions remain proposal/decision artifacts (Stage 5.8); no automated
  commit/push outside an explicitly approved run.

## 11. No Direct AI Push Rule

No Stage 6 component may push work to any AI agent (local or remote)
directly. All AI-bound work flows through: prompt packet (5.4) → operator
review (5.5) → either manual handoff or an activated adapter (6.5), where
the adapter path additionally requires a persisted per-dispatch approval.
There is no code path from command intake to AI dispatch that skips the
operator.

## 12. Manual Fallback Rule

Every AI-related workflow must remain fully executable manually: the
Stage 5.5 manual handoff packages and Stage 5.9 operator runbooks are
maintained and kept working throughout Stage 6. Adapter activation (6.5)
adds an automated option; it never replaces the manual path. If an adapter
fails or is deactivated, the workflow degrades to manual, not to broken.

## 13. No Cloud Dependency Rule

Stage 6 introduces no cloud dependency — no hosted compute, storage,
telemetry, queueing, or third-party runtime service. All gates, tests, and
the backend itself run offline. Cloud usage of any kind requires a later,
separately-approved stage with its own boundary document; nothing in
Stage 6 pre-authorizes it.
