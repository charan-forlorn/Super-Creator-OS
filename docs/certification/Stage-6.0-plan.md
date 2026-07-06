# Stage 6.0 Plan — Stage 6 Handoff Review & Execution Plan

Predecessor: Stage 5.10 (Stage 5 final AI command center certification,
closed at commit `4ce48a1`, gate GO, readiness 100/100, zero blockers).

## 1. Stage goal

Review the Stage 6 handoff, convert it into a clear execution plan, define
Stage 6 boundaries, group the work into no more than 10 focused items, and
prepare Stage 6 for implementation. Planning / review / execution-design
only.

## 2. Scope

Documentation only:

- `docs/roadmap/STAGE6_EXECUTION_PLAN.md`
- `docs/specification/STAGE6_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md`
- `docs/roadmap/STAGE6_HANDOFF_REVIEW.md`
- `docs/certification/Stage-6.0-plan.md` (this file)

## 3. Non-goals

- No Stage 6 feature implementation (no backend, API routes, database,
  WebSocket, agent dispatch, timers, workers).
- No runtime behavior changes; no changes to `scos/`,
  `apps/control-center/`, or package files.
- No Stage 6.1 code; no Stage 4/5 reopening or contract changes.
- No cloud/SaaS/payment/CRM surface.
- No commit/push/tag/release performed by this stage's execution.

## 4. Source files reviewed

- `docs/roadmap/STAGE6_HANDOFF.md` (source of truth; unmodified)
- `docs/certification/Stage-5-final-ai-command-center-certification.md`
- `docs/roadmap/STAGE5_HANDOFF.md`
- `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`

## 5. Files created

The five documents listed under Scope. No files modified, none deleted.

## 6. Architecture decisions

1. Stage 6 lives entirely in the Operator Tools Layer
   (`scos/control_center/`, `apps/control-center/`), contract-coupled per
   the boundary constitution.
2. The Stage 6 backend is a single local process, localhost-only; Stage 6
   defines its own explicit safety boundary
   (`STAGE6_SCOPE_BOUNDARY.md`) rather than inheriting Stage 5's mock-only
   boundary by default.
3. Operator approval remains the permanent safety boundary; a persisted
   approval record precedes every approvable action, including any future
   real AI dispatch.
4. Manual fallback (Stage 5.5 handoff packages, 5.9 runbooks) is preserved
   through all of Stage 6; adapter activation (6.5) is additive and
   decision-first.
5. Durability moves from JSONL to SQLite WAL only where required (6.3), with
   deterministic, evidenced migration and append-only audit semantics.
6. The handoff's "defects carried forward" vs. the certification's
   "already remediated" conflict is resolved by scoping Stage 6.1 as
   verification/re-certification (see `STAGE6_HANDOFF_REVIEW.md`).

## 7. Proposed Stage 6 sequence

6.1 (hard prerequisite) → 6.2 → 6.3 → {6.4, 6.6} → 6.5 (after 6.6) →
6.7/6.8 (parallelizable) → 6.9 → 6.10 (final gate). Exactly 10 items; patch
sub-stages only for blocker/build/deploy/certification failures or wrong
decision data.

## 8. Stage 6.1 recommendation

**Stage 6.1 — Stage 5.6 defect verification & Stage 5.10 gate
re-confirmation:** verify the six remediated Stage 5.6 defects at HEAD
(`4ce48a1`), re-run `run_stage5_final_certification` with a fresh
`checked_at`, confirm GO / zero error-critical blockers / clean tree, and
record evidence. Expand to the isolated patch only if a defect is actually
unfixed.

## 9. Validation commands

Preflight (all passed before writing):

```
git fetch origin
git status --short --untracked-files=all   # clean
git rev-parse HEAD                          # 4ce48a1...
git rev-parse origin/main                   # 4ce48a1... (== HEAD)
git branch --show-current                   # main
git log --oneline -12                       # Stage 5 final commits present
```

Post-write validation (read-only):

```
git status --short --untracked-files=all
git diff -- docs/roadmap/STAGE6_EXECUTION_PLAN.md docs/specification/STAGE6_SCOPE_BOUNDARY.md docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md docs/certification/Stage-6.0-plan.md
git diff --stat
```

Expected: status shows only the five new untracked docs files; both diffs
empty (no tracked file changed).

## 10. PASS criteria

- STAGE6_HANDOFF.md reviewed; Stage 6 objective, theme, and boundaries
  documented; exactly 10 work items defined with owner/risk/dependency;
  Stage 6.1 clearly recommended.
- Stage 6 non-goals, acceptance criteria, safety rules, and risk register
  documented.
- Docs-only change set: no modifications to `scos/`,
  `apps/control-center/`, package files, or Stage 4/5 contracts; no
  API/backend/network/cloud behavior introduced.
- Stage 4 and Stage 5 remain closed; no commit/push/tag/release performed.

## 11. Known risks

See the full risk register in `STAGE6_EXECUTION_PLAN.md` §15. Headlines:
building on unverified Stage 5.6 fixes (mitigated by 6.1-first), the
backend as a boundary change (mitigated by the Stage 6 scope boundary doc),
and real AI dispatch (mitigated by 6.6-before-6.5 and the per-dispatch
approval rule). No current blockers.

## 12. Would-be commit message

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
