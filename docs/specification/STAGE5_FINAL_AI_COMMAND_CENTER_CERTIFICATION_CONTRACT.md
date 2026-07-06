# Stage 5 Final AI Command Center Certification Contract

## Purpose

Stage 5.10 is a read-only certification gate over the Stage 5.1-5.9 local AI
Command Center foundation (`scos/control_center/`, `apps/control-center/`).
It answers one question: is Stage 5 complete, internally consistent, locally
verifiable, safe from real AI dispatch / network / automation overreach, and
ready to hand off to Stage 6?

It never fixes anything it finds. Known, pre-existing defects in the
inspected Stage 5.1-5.9 artifacts are reported as blockers, not silently
repaired or downgraded.

## Scope

- Inspects `scos/control_center/`, `scos/control_center/tests/`,
  `docs/specification/`, `docs/certification/`, `docs/roadmap/`,
  `apps/control-center/`, and `scripts/`.
- Verifies Stage 5.1-5.9 source, contract docs, frontend panels, and tests
  exist and are internally consistent (package exports, module docstring
  convention, frontend wiring).
- Verifies the workflow continuity chain (command bridge -> work session ->
  adapter contract -> prompt/result packet -> operator packet review ->
  cross-agent router -> result intake -> git approval -> operator execution
  runbook) as an existence/contract check only - it never executes anything.
- Verifies the local/approval-first safety boundary: no real AI dispatch, no
  network/API/browser/GUI/clipboard automation, no backend server, no
  database, no WebSocket/polling/timer/worker, no CRM/payment/billing/SaaS.
- Runs (or documents) the Stage 5.1-5.9 test files, `scripts/test_smoke.py`,
  and `scripts/security_scan_baseline.py`.
- Optionally runs `pnpm lint` / `pnpm build` from `apps/control-center` only
  (never `pnpm install`, never a package.json write).
- Produces a deterministic certification result and a Stage 6 handoff plan.

## Non-goals

- Does not fix any Stage 5.1-5.9 defect it finds.
- Does not add new Stage 5 feature work (Stage 5 ends at 5.10; a
  stage-over-fragmentation scan enforces this).
- Does not dispatch real AI work, open a network connection, automate a
  browser/GUI, or touch the clipboard.
- Does not introduce a backend server, API route, database, or any
  timer/polling/WebSocket behavior.
- Does not modify Stage 5.1-5.9 public contracts. The only permitted
  `__init__.py` change is an append-only block exporting Stage 5.10's own
  public symbols.

## Safety boundaries

| Boundary | Enforcement |
|---|---|
| No real AI dispatch | `validate_no_real_ai_dispatch` scans the Stage 5.3 adapter modules for real model-API import statements |
| No forbidden backend behavior | `validate_backend_forbidden_tokens` scans all of `scos/control_center/*.py` (excluding this stage's own two files) for network/shell/GUI-automation/clipboard-automation import statements and `shell=True`/`os.system(` call sites |
| No forbidden frontend behavior | `validate_frontend_forbidden_tokens` scans `apps/control-center/**/*.{ts,tsx}` for fetch/XHR/WebSocket/timer/storage/clipboard tokens, skipping comments and documented negations |
| No backend API surface | `validate_no_app_api_or_middleware` confirms no `app/api` directory, `route.ts`, or `middleware.ts` exists |
| subprocess allowlist | `validate_subprocess_allowlist_exception` confirms `command_runner.py` is the only importer, uses list argv, a finite timeout, and never `shell=True` |
| Self-check | `validate_stage5_10_own_files_forbidden_tokens` dogfoods the same scan against Stage 5.10's own two new files |

## Certification checks

Checks are grouped by category (`preflight`, `source_contract`,
`workflow_continuity`, `safety_boundary`, `frontend_static_scope`,
`testing`, `security`, `stage6_handoff`, `stage5_readiness`). See
`scos/control_center/stage5_final_certification.py::_SCORE_BUCKETS` for the
authoritative, versioned list of every check name, its bucket, and its
weight.

## Readiness score rules

- `readiness_max_score` is always `100`.
- Score is computed per category bucket: any `failure` in a bucket zeroes
  that bucket's weight; a `skipped` status with no failure halves it
  (floored); otherwise the bucket earns its full weight.
- Bucket weights: preflight 5, source_contract 20, workflow_continuity 15,
  safety_boundary 20, frontend_static_scope 5, testing 15, security 5,
  stage6_handoff 5, stage5_readiness 10 (sum = 100).
- `git_state` is informational only (`warning` severity at worst) - a dirty
  tree or non-main branch never blocks GO by itself, since Stage 5 has no
  release/tag policy of its own.

## GO / NO_GO rule

```
has_error_or_critical = any blocker with severity in (error, critical)
if has_error_or_critical or score < 90:      -> NO_GO, blocked
elif score == 100 and no blockers at all:    -> GO,    certified
else:                                        -> GO,    conditionally_ready
```

`stage_closed` is `True` only when `accepted` is `True` (i.e. `GO`) and
there is zero error/critical blocker - enforced both by this rule and by a
model-level invariant in `Stage5FinalCertificationResult.__post_init__`.

A real repo containing the known Stage 5.6 export gap and/or the duplicate
`ALLOWED_COMMAND_TYPES` lazy-export key will correctly certify **NO_GO**
until those are fixed in a later, separately-approved change.

## Stage 6 handoff requirements

The gate always generates 10 deterministic `Stage6HandoffItem` entries
(`stage6-001`..`stage6-010`) covering: the real Control Center backend and
command API, the operator event stream, the Stage 5.6 export-gap fix, the
duplicate lazy-export key fix, wiring `workflow-router-panel` into the app
shell, cleaning the stray Stage 5.6 README line, deciding which agent
adapters become real dispatchers (always behind operator approval),
executing the remaining Stage 5 handoff gates from `STAGE5_HANDOFF.md`,
adding an automated frontend test tier, and defining Stage 6's own success
criteria and closure gate.

## Deterministic output contract

- `certification_id = "s5c-" + sha256(f"stage5-final-certification|{checked_at}|{resolved_repo_root}")[:16]`.
- No `datetime.now`, `uuid`, or `random` anywhere in the gate or its models;
  `checked_at` is always caller-supplied.
- Output JSON (only written when `output_path` is given) is
  `json.dumps(payload, sort_keys=True, indent=2)` with a trailing `\n`,
  UTF-8, LF-only line endings.
- The gate never mutates any inspected Stage 5.1-5.9 artifact; the only
  write it performs is this single output JSON file.
