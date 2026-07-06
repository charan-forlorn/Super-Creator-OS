# Stage 6 Acceptance Criteria

Normative acceptance criteria for Stage 6 (Local Control Center Real
Integration). Companion to `docs/roadmap/STAGE6_EXECUTION_PLAN.md` and
`docs/specification/STAGE6_SCOPE_BOUNDARY.md`. Defined by Stage 6.0.

## 1. Stage 6 Entry Criteria

Stage 6 implementation (6.1 onward) may begin only when:

- Stage 4 is closed (Stage 4.19 gate GO) and Stage 5 is closed (Stage 5.10
  gate GO, `stage_closed = True`, zero blockers) — both currently true at
  commit `4ce48a1`.
- `docs/roadmap/STAGE6_HANDOFF.md` exists and the Stage 6.0 planning
  artifacts (execution plan, scope boundary, this document, Stage-6.0-plan
  certification) are committed.
- Working tree clean, `HEAD == origin/main`, branch `main`.
- The Stage 6.x task in question is explicitly approved by the operator;
  Stage 6.0 itself authorizes no implementation.

## 2. Stage 6 Per-Stage Acceptance Criteria Template

Every Stage 6.x closes against this template:

1. **Goal met** — the stage's stated goal (per the execution plan work item)
   is demonstrably achieved.
2. **Scope respected** — changes touch only the stage's allowed files/scope;
   no forbidden-scope violations (`STAGE6_SCOPE_BOUNDARY.md`).
3. **Tests green** — new/changed modules have tests following the repo
   convention; the relevant test tiers (Section 4) pass locally, offline.
4. **Safety preserved** — command validation, operator approval, local-first,
   and manual-fallback rules verifiably intact; no bypass path introduced.
5. **Evidence recorded** — a `docs/certification/Stage-6.x-plan.md` (or gate
   report) documents goal, scope, files, validation commands, and results.
6. **Docs updated** — contracts, READMEs, and roadmap docs affected by the
   stage are updated in the same stage.
7. **Git safety** — work committed on `main` per repo convention, clean tree
   after commit, no force-push, no history rewrite, gate-relevant re-runs
   done against the committed tree.
8. **No fragmentation** — no Stage 6.x.y sub-stages except a blocker patch
   (blocker, build fail, deploy fail, certification fail, or wrong decision
   data).

## 3. Stage 6 Final Acceptance Criteria

Stage 6 as a whole passes when:

- Stage 6.1: Stage 5.10 gate re-run returns `GO` with zero error/critical
  blockers on a clean committed tree.
- Stage 6.2: every command flows draft → validate → operator approval →
  queue → allowlisted runner → event log; no API path bypasses validation or
  approval; contract tests green; localhost-only.
- Stage 6.3: all Stage 5 state types round-trip through the SQLite WAL
  store; JSONL→SQLite migration deterministic and evidenced; audit records
  append-only.
- Stage 6.4: Control Center UI reflects backend state end-to-end for at
  least one real command; replay from the persisted event log reproduces UI
  state deterministically.
- Stage 6.5: written activation decision precedes any dispatch code; every
  real dispatch has a prior persisted approval record; manual fallback
  demonstrated still working.
- Stage 6.6: no approvable action executes without a persisted decision;
  audit trail survives restart; denial paths tested.
- Stage 6.7: a real frontend test runner exists and passes locally with
  baseline coverage of panel wiring and command/approval flows.
- Stage 6.8: extended security scan passes over `scos/control_center` and
  `apps/control-center` (or findings documented and accepted).
- Stage 6.9: backend health and recent activity determinable from local
  artifacts via re-runnable, offline-safe checks.
- Stage 6.10: the Stage 6 gate exists, is deterministic and re-runnable, and
  returns `GO` / `accepted = True` / `stage_closed = True` with zero
  error/critical blockers.

## 4. Required Tests / Validation Tiers

- **Tier 1 — module tests:** per-module test files with the repo's
  sys.path-bootstrap + `__main__` runner convention; run directly, offline.
- **Tier 2 — contract tests:** command/result envelopes, event log schema,
  approval lifecycle, persistence round-trips validated against
  `docs/specification/*_CONTRACT.md`.
- **Tier 3 — frontend checks:** `pnpm lint`, `pnpm build`, and (from 6.7)
  the frontend test script — required when `pnpm`/`node_modules` available,
  skip-clean otherwise.
- **Tier 4 — repo tiers:** `scripts/test_smoke.py` and
  `scripts/security_scan_baseline.py` remain green throughout.
- **Tier 5 — gates:** Stage 4.19 and Stage 5.10 gates re-runnable and GO at
  Stage 6 close; Stage 6.10 gate green.
- All tiers run locally with no network and no real AI dispatch.

## 5. Required Certification Evidence

Per stage: `docs/certification/Stage-6.x-plan.md` containing goal, scope,
non-goals, files changed, validation commands with results, PASS criteria,
risks, and commit message. For gate stages (6.1, 6.10): the gate's
machine-produced report values (go/no-go, readiness score, blockers,
`checked_at`) recorded verbatim. Evidence artifacts are deterministic and
reproducible from the committed tree plus the recorded `checked_at`.

## 6. Required Frontend Validation (if UI is touched)

Any stage touching `apps/control-center/` must: pass `pnpm lint` and
`pnpm build`; from Stage 6.7 onward also pass the frontend test script;
wire new panels into `app-shell.tsx` and `sidebar.tsx` `NAV_SECTIONS`
following the existing per-stage section convention (the Stage 5.6 wiring
gap is the cautionary precedent); and update
`apps/control-center/README.md` with a stage section in chronological order.

## 7. Required Security / Static Scans

- `scripts/security_scan_baseline.py` green (with Stage 6.8's extended
  coverage once landed) before any stage closes after 6.8, and mandatorily
  before 6.10.
- No secrets, tokens, or credentials in the diff, logs, event streams, or
  evidence docs.
- New listeners verified localhost-only; new subprocess calls verified
  allowlist-mediated; no `shell=True` introductions without review.

## 8. Required Git Safety Checks

Per stage close: branch `main`; `HEAD == origin/main` after push; working
tree clean (`git status --short --untracked-files=all` empty); no
force-push, rebase of published history, tag, or release without explicit
approval; commit messages follow the repo's `type(scope): subject`
convention; gate re-runs performed against the committed tree.

## 9. Required Docs Update Checks

- Contract changes land in `docs/specification/` in the same stage as the
  code that implements them.
- `docs/roadmap/STAGE6_EXECUTION_PLAN.md` risk register/status updated when
  a stage close materially changes it.
- Certification evidence per Section 5.
- Stage 6.10 produces `docs/roadmap/STAGE7_HANDOFF.md` and the Stage 6
  closure statement.

## 10. Stage 6 Close Gate

Stage 6 is closed only when the Stage 6.10 gate — deterministic,
re-runnable, offline, non-mutating, mirroring the Stage 4.19 / Stage 5.10
pattern — returns `go_no_go = GO`, `accepted = True`, `stage_closed = True`,
zero error/critical blockers, against a clean tree with
`HEAD == origin/main`; Stage 4.19 and Stage 5.10 gates still return GO; the
Stage 7 handoff exists; and an over-fragmentation scan finds no Stage 6.11+
markers. After close, no further Stage 6.x feature work is authorized —
new work is Stage 7 backlog.
