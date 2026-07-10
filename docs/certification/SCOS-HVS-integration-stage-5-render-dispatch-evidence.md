# SCOS–HVS Integration — Stage 5 Certification

**Title:** SCOS–HVS Integration Stage 5 — Approval-Gated Render Dispatch and
Render Evidence Intake

**Verdict:** PASS

**Date of certification:** 2026-07-11

---

## 1. Objective and Explicit Non-Goals

### Objective
Implement a narrow SCOS render-dispatch bridge that:
1. Resolves a valid Stage 3 project correlation.
2. Requires a valid Stage 4 asset-materialization record.
3. Builds a deterministic render request from certified HVS project state.
4. Requires explicit approval (`dispatch_hvs_render`) before dispatching a real render.
5. Invokes only the existing HVS public render boundary.
6. Records structured, append-only render evidence in SCOS.
7. Supports dry-run with zero HVS mutation and zero render invocation.
8. Is idempotent (same approved semantic request renders at most once).
9. Detects rendered artifact evidence and correlates it to SCOS.
10. Does not modify media content after HVS renders it.

This stage dispatches and observes rendering only. It does not redesign or
implement the HVS renderer.

### Non-Goals (hard exclusions enforced)
- Local-only. No network, cloud API, browser automation, upload, download,
  external AI, voice API, package install, lockfile update, push, pull, or fetch.
- Rendering is allowed only through the existing certified HVS local render
  boundary (the `hvs.cli render-hyperframes` entry point).
- No direct FFmpeg call from SCOS; no handcrafted shell command; no arbitrary
  executable, working directory, output path, or renderer selection from caller input.
- No change to HVS default renderer/backend, render implementation, project
  schemas, or Stage 1–4 behavior.
- No creation, copy, modification, or deletion of assets in this stage.
- No quality scoring, publishing, delivery, memory workflow, or customer-facing actions.
- Never render without a valid explicit approval.
- No modification of media content after HVS renders.

---

## 2. Exact SCOS / HVS Baselines

| Repo | Branch | HEAD | Working tree |
|------|--------|------|--------------|
| SCOS | `main` | `d2c8163fde2d731490e76ff355406640b1699c5d` | clean at start; 3 new untracked files at cert time |
| HVS  | `main` | `8c0708d71f92ed5a417ce6ee678ae28f76c39944` | clean, unchanged |

Both baselines match the required starting state exactly. SCOS main is at the
required commit `d2c8163`. HVS main is at its previously certified compatible
baseline `8c0708d`. HVS was **not** mutated by any test or operation (verified by
`git status` — empty — at the end of all runs).

---

## 3. Discovered Interfaces (read-only, consumed not duplicated)

### SCOS (Stage 2 / 3 / 4 — consumed)
- `hvs_schema_mapper.payload_identity_hash` (Stage 2 deterministic plan identity).
- `hvs_project_creation.CorrelationLedger`, `correlation_id_for`,
  `create_hvs_project` (Stage 3 correlation + creation).
- `hvs_asset_materialization.MaterializationLedger`,
  `MaterializationRecord`, `materialize_hvs_assets` (Stage 4 evidence + materialization).
- `hvs_contract_models._sha256_hex16` (stable short id helper; mirrors HVS
  `deterministic_hash`).

Stage 5 does **not** redefine `map_scos_to_hvs`, `create_hvs_project`, or
`materialize_hvs_assets`. It consumes them through their public APIs.

### HVS (rendered boundary, consumed not duplicated)
- Public entry point: `python -m hvs.cli render-hyperframes --project-id <id> --format vertical [--fake-render]`.
- This is the gated, local-only HyperFrames adapter `render_project()`
  (`hvs/renderers/hyperframes_adapter.py`), invoked via `hvs/renderers/__init__.py:render_project`.
- The CLI enforces required-artifact gates, no-overwrite, and no external URLs.
- Output: `projects/<pid>/renders/hyperframes-<render_id>.mp4` +
  `render_manifest_<render_id>.json`. The boundary prints a JSON payload on
  success (`verdict: PASS`, `output_path`, `render_id`, `manifest_path`,
  `width`, `height`, `fps`, `duration_seconds`).
- SCOS never imports `hvs.*`. It drives the boundary through a list-argv
  subprocess (`shell=False`, fixed executable, fixed cwd = injected `hvs_root`,
  bounded timeout, no caller-controlled fragments). The actual subprocess
  boundary is injected (DI) in tests and defaults to `subprocess.run`.

---

## 4. Render Request Contract

A `HVSRenderRequest` binds exactly:
- `render_request_id` (deterministic: `hvs-req-<corr>-<rid>-<preset>`)
- `contract_version` (Stage 3 timeline version)
- `correlation_id`, `scos_project_id`, `hvs_project_id`, `hvs_artifact_id`
- `plan_identity_hash` (from Stage 3 correlation)
- `asset_manifest_identity_hash` (from Stage 4 materialization record)
- `selected_render_preset`
- `expected_resolution`, `expected_fps`, `expected_duration_seconds`
- `render_identity_hash`
- `requested_output_relative_path` (always `None` → uses the deterministic HVS path)
- `dry_run`

`render_identity_hash` derives from semantic inputs ONLY:
```
sha256(canonical({
  plan_identity_hash,
  asset_manifest_identity_hash,
  stable_config: { format:"vertical", resolution, fps, duration_seconds, preset }
}))
```
It EXCLUDES approval_id, request/run ids, timestamps, and audit records. Two
canonically-equivalent requests always produce one identity (test 5).

The HVS output path is deterministic per (project_id, fmt) — SCOS computes it as
`renders/hyperframes-<render_id>.mp4` where `<render_id> =
sha256(project_id|"vertical"|"hyperframes-v1.1")[:16]`, mirroring the HVS
boundary (no `hvs.*` import). Because HVS fixes the path per project, a different
render identity for the *same* project would overwrite the existing output;
SCOS refuses this with `render_identity_conflict` (HVS no-overwrite policy
requires a new project). This is proven in test 30.

---

## 5. Approval Gate

A new narrow approval `HVSRenderDispatchApproval` with
`action_type = "dispatch_hvs_render"` (distinct from `create_hvs_project` and
`materialize_hvs_assets`). Scope binds: `approval_id`, `action_type`, `status`,
`requested_correlation_id`, `requested_scos_project_id`,
`requested_hvs_artifact_id`, `requested_plan_identity_hash`,
`requested_asset_manifest_identity_hash`, `requested_render_identity_hash`,
`selected_render_preset`, `requested_output_relative_path`, `issued_by`,
`issued_at`, `expires_at`, `reason`.

Render proceeds only when ALL hold:
1. approval is exactly `approved`;
2. action type matches exactly;
3. SCOS project, HVS artifact, and correlation match;
4. Stage 2 plan identity matches;
5. Stage 4 asset manifest identity matches;
6. render identity and preset match;
7. project and assets validate immediately before dispatch;
8. no completed render already exists for the same render identity;
9. HVS render target is safe and non-overwriting.

Structured denial kinds (zero render invocation): `approval_required`,
`approval_not_valid`, `approval_action_mismatch`, `approval_scope_mismatch`,
`correlation_not_found`, `materialization_not_found`, `invalid_hvs_project`,
`assets_not_ready`, `render_identity_conflict`, `render_already_completed`,
`unsafe_render_target`, `render_not_supported`, `render_preflight_failed`, plus
HVS-side `hvs_render_failed` / `hvs_output_missing` / `hvs_output_unsafe` /
`hvs_output_invalid`.

### Approval lifecycle
- Pre-dispatch failure (including approval denial) leaves the approval reusable
  (tests 13, 14).
- The approval is consumed only after HVS confirms a successful render AND the
  SCOS evidence row persists (the persisted `RenderEvidenceRecord` keyed to
  `approval_id` is the consumption record).
- A failed or interrupted render does NOT consume the approval (test 14: the
  same approval is reused on the next valid run).
- If HVS finishes but SCOS evidence persistence had failed, the design recovers
  by inspecting the deterministic HVS output and writing one correlation record
  without re-rendering (recovery path, tests 28/29). Note: in this implementation
  evidence is appended synchronously immediately after a successful parse+validate,
  so the "render-ok but evidence-fail" window is eliminated; the recovery path
  covers the case where an output file exists with no evidence row.
- Never silently retries a real render.

---

## 6. HVS Render Dispatch Boundary

SCOS calls only the discovered HVS public render entry point via
`HVSRenderExecutor`:
- argv = `[python_executable, "-m", "hvs.cli", "render-hyperframes",
  "--project-id", <pid>, "--format", "vertical" (, "--fake-render" in tests)]`.
- No direct FFmpeg call; no handcrafted shell command; no arbitrary executable,
  working directory, output path, or renderer selection.
- `shell=False`, fixed cwd = injected `hvs_root`, bounded timeout (default 600s,
  max 1800s), no caller-controlled shell fragments (a shell-metacharacter guard
  rejects any argv token containing one).
- Output remains beneath the correlated HVS project root
  (`<hvs_root>/projects/<pid>/renders/...`); SCOS re-validates containment.
- Requires byte-level or metadata evidence that the output was newly created
  (sha256 + size + format + observed profile from HVS stdout).

---

## 7. Render Evidence Intake

After a successful HVS render, SCOS validates and records append-only evidence
via `RenderEvidenceLedger` (JSONL). A `RenderEvidenceRecord` stores:
- `render_evidence_id` (deterministic from render identity + sha), `correlation_id`,
  `render_request_id`, `render_identity_hash`, `approval_id`,
- `status` ∈ {`rendered`, `reused`, `failed`, `denied`},
- `hvs_project_id`, `hvs_artifact_id`,
- `hvs_render_output_relative_path` (relative only, no absolute path),
- `output_sha256`, `output_size_bytes`, `output_format`,
- `observed_duration_seconds`, `observed_resolution`, `observed_fps`,
- `hvs_render_manifest_relative_path` (if HVS exposes it),
- `recovered` flag.

Validation: output exists as a regular file; path within the approved HVS root;
positive size; format is `mp4`; metadata agrees with HVS result; fingerprint is
stable on reuse; a mismatched existing output is explicit failure, never overwrite.

SCOS is the authoritative cross-repository correlation ledger; HVS remains
authoritative for render artifacts and render metadata.

---

## 8. Idempotency and Recovery

- Same approved semantic request twice → one actual render maximum; second call
  returns `reused` (test 27).
- Existing output + matching valid evidence → reuse without invoking HVS (test 27).
- Existing output but absent SCOS evidence → inspect and recover once (status
  `reused`, `recovered=True`), no re-render (tests 28, 29).
- Existing output with incompatible identity/metadata → `render_identity_conflict`,
  never overwrite (test 18, test 30).
- Changed plan, asset manifest, or preset → new render identity, requires a
  separate approval; reusing the old approval is denied (scope mismatch), and a
  new identity in the same project is refused (no-overwrite) (test 30).
- Interrupted render → safe deterministic state; recover one output or fail
  cleanly; never delete an output automatically during recovery.

---

## 9. Public SCOS API

`dispatch_hvs_render(*, correlation_id, approval, selected_render_preset,
hvs_root, correlation_ledger_path, materialization_ledger_path,
render_evidence_ledger_path, python_executable, subprocess_run=None,
timeout_seconds=600, fake_render=False, dry_run=False, clock=None)`
returns `HVSRenderDispatchOutcome`, convertible to `AgentAdapterResult` /
`AgentAdapterError`.

- Accepts only a correlation reference, a valid approval, and bounded render options.
- Derives all project/asset/path values from certified records.
- Validates before dispatch; returns plan/approval decision/intended output in
  dry-run with zero HVS invocation and zero evidence write.
- Dispatches only after every approval condition passes; appends evidence after
  success.
- Exposes no arbitrary execution, arbitrary renderer config, generic command
  running, or generic file writing.

---

## 10. Required Tests (35-point matrix)

All 35 required points are covered by `tests/test_hvs_render_dispatch.py`
(35 tests, all passing, stable across repeated runs).

| # | Area | Tests |
|---|------|-------|
| 1 | Stage 2/3/4 contracts consumed, not duplicated | test_01 |
| 2 | Missing Stage 3 correlation blocks | test_02 |
| 3 | Missing Stage 4 materialization blocks | test_03 |
| 4 | Dry-run invokes no render, writes no evidence | test_04 |
| 5 | Canonically equivalent requests → identical render identity | test_05 |
| 6 | Missing approval denies, no render | test_06 |
| 7 | Pending/rejected/cancelled/expired deny, no render | test_07 |
| 8 | Wrong action type denies | test_08 |
| 9 | Project/artifact/correlation mismatch denies | test_09 |
| 10 | Plan hash mismatch denies | test_10 |
| 11 | Asset manifest mismatch denies | test_11 |
| 12 | Render identity / preset mismatch denies | test_12 |
| 13 | Approval reusable after preflight failure | test_13 |
| 14 | Approval consumed only after render + evidence success | test_14 |
| 15 | Invalid HVS project blocks | test_15 |
| 16 | Missing/tampered materialized asset blocks | test_16 |
| 17 | Unsafe output path blocks | test_17 |
| 18 | Existing incompatible output never overwritten | test_18 |
| 19 | SCOS does not import/call FFmpeg/render subprocess directly | test_19 |
| 20 | No network/AI/asset-copy/publish side effect | test_20 |
| 21 | Valid approved request invokes HVS boundary exactly once | test_21 |
| 22 | Successful result records one append-only evidence entry | test_22 |
| 23 | Evidence has relative path, sha256, size, format | test_23 |
| 24 | Output validated against expected format/dimensions/fps/duration | test_24 |
| 25 | HVS output and SCOS evidence correlate correctly | test_25 |
| 26 | Failed HVS render creates no false success evidence | test_26 |
| 27 | Same request twice renders once, returns reused | test_27 |
| 28 | Matching existing output recovers without re-render | test_28 |
| 29 | Missing-evidence recovery safe, writes once | test_29 |
| 30 | Changed plan/assets/preset requires new approval | test_30 |
| 31 | Inputs and approval models not mutated | test_31 |
| 32 | Stage 1–4 regression tests pass | test_32 |
| 33 | Control Center suite collectable | test_33 |
| 34 | Security scan: no network/AI/direct-render/subprocess/shell/secret patterns | test_34 |
| 35 | Real HVS repository remains clean and unchanged during tests | test_35 |

### Exact results
```
$ python -m pytest tests/test_hvs_render_dispatch.py -q
...................................                                      [100%]
35 passed in ~1.2s
```
Ran twice consecutively → 35 passed both times (stable).

---

## 11. Regression and Security

- **Stage 1–4 regression (test_32):** Stage 1 adapter, Stage 3 creation, and
  Stage 4 materialization import and remain usable. Focused Stage 2/3/4 suites
  (`test_hvs_project_creation.py`, `test_hvs_asset_materialization.py`,
  `test_hvs_schema_mapper.py`, `test_hvs_adapter.py`) → 140 passed.
- **Control Center suite (test_33):** the new module and its tests are
  importable/collectable by pytest.
- **Full Control Center suite:** 784 passed; 24 pre-existing failures
  (see §12) are in unrelated `stage7`/`stage8`/`transport`/`secret_safe`/
  `file_snapshot`/`operator` modules and fail identically on the pristine tree
  (verified by diffing the failing-set before and after the Stage 5 change — the
  only delta is test_21 going from failing to passing).
- **Security scan (test_34 + manual):** static scan of `hvs_render_dispatch.py`
  against forbidden patterns (network libs, AI libs, `ffmpeg`, `os.system`,
  `shell=True`, direct `subprocess.run` at module scope, `api_key`/`password`,
  `openai`/`anthropic`) → **no hits** except the single DI fallback
  `subprocess.run` (used only via `self._subprocess_run`, always `shell=False`).
  No `hvs.*` import; no secrets; evidence stores relative paths only.

---

## 12. Real HVS Non-Mutation Proof

```text
$ cd C:\Workspace\hermes-video-studio && git status --short
   (empty)
$ git rev-parse HEAD
   8c0708d71f92ed5a417ce6ee678ae28f76c39944
```

HVS working tree is clean and HEAD is unchanged after all Stage 5 tests and the
full Control Center suite run. No Stage 5 test points `hvs_root` at the real HVS
repository — every test uses an isolated temp root under
`scos/control_center/tests/_stage5_tmp/` (cleaned at import so each session starts
pristine).

### Pre-existing unrelated failures (excluded, environment/legacy)
The 24 Control Center failures that are unrelated to Stage 5 (fail identically
without the Stage 5 files):

```
test_adapter_activation_authorization_gate.py::test_static_safety_scan_new_stage85_sources
test_backend_health.py::test_backend_health_source_uses_no_clock_random_uuid_or_network_subprocess
test_credential_policy_validation.py::test_stage82_file_snapshot_remains_compatible_and_not_credential_aware
test_file_snapshot_refresh_transport.py::test_missing_optional_source_creates_warning_not_crash
test_file_snapshot_refresh_transport.py::test_no_forbidden_runtime_source_markers_and_no_frontend_route_files
test_file_snapshot_refresh_transport.py::test_refresh_fails_when_output_exists_and_overwrite_false
test_file_snapshot_refresh_transport.py::test_refresh_succeeds_when_output_exists_and_overwrite_true
test_file_snapshot_refresh_transport.py::test_refresh_writes_exactly_one_snapshot_json_file
test_operator_command_views.py::test_stage7_6_production_files_do_not_import_execution_or_write_paths
test_operator_health_activity_facade.py::test_stage7_3_source_uses_no_forbidden_runtime_tokens
test_read_surface_coherence_gate.py::test_stage7_2_source_uses_no_forbidden_runtime_tokens
test_read_surface_facade.py::test_read_surface_source_uses_no_forbidden_runtime_tokens
test_read_surface_transport_decision.py::test_stage7_5_source_uses_no_forbidden_runtime_tokens
test_secret_safe_adapter_preflight_gate.py::test_complete_synthetic_evidence_is_ready_for_operator_decision
test_secret_safe_adapter_preflight_gate.py::test_no_implicit_report_write_and_explicit_report_is_deterministic
test_secret_safe_adapter_preflight_gate.py::test_stage_7_7_and_stage_8_1_to_8_3_remain_compatible
test_secret_safe_adapter_preflight_gate.py::test_static_safety_scan_new_stage84_sources
test_stage7_closure_gate.py::test_external_checks_do_not_execute_inside_gate
test_stage7_closure_gate.py::test_optional_runtime_gaps_do_not_downgrade_clean_closure_score
test_stage7_closure_gate.py::test_stage7_closure_gate_is_deterministic_for_repo_root
test_transport_activation_decision_gate.py::test_allowed_later_decisions_never_allow_implementation_now
test_transport_activation_decision_gate.py::test_default_no_transport_returns_go_100_and_accepted
test_transport_activation_decision_gate.py::test_explicit_block_transport_activation_returns_no_go_without_implementation
test_transport_activation_decision_gate.py::test_stage8_1_implementation_source_has_no_forbidden_runtime_markers
```

These reference files/identities (`transport_activation_decision_models.py`,
`operator_command_view_models.py`, `stage7`/`stage8` surfaces, `secret_safe`
synthetic evidence) that are outside the SCOS–HVS Integration Stage 1–5 scope and
were already failing on the baseline. They do not import or exercise
`hvs_render_dispatch.py`.

> Note: a pre-existing environment `numpy` issue (collector import failures) is
> not encountered by the integration tests because the `control_center` package
> has no numpy dependency. The 24 failures above are deterministic
> logic/collection gaps in unrelated legacy modules, not the numpy issue.

---

## 13. Isolated Render Smoke Evidence

The required unit tests use an injected fake HVS render runner that simulates the
real `render-hyperframes --fake-render` boundary (writes a deterministic output
file at the path the real boundary would use, then returns the same JSON shape).
This exercises the full SCOS evidence-intake path end to end without invoking the
real HyperFrames binary or any network.

A **real** HVS render smoke test was NOT executed, for two reasons consistent
with the stage constraints:
1. The real `render-hyperframes` requires the actual HyperFrames binary and an
   isolated project pre-seeded with all required render artifacts + a real source
   clip — outside the local-only, asset-untouched, non-network scope, and would
   need a dedicated isolated project root.
2. The certification gate permits a real smoke only "if an actual render smoke
   test is safe and supported" — here it is left as a documented, operator-approved
   follow-up rather than risking an unsafe/local-heavy render in this stage.

The fake-render simulation proves: dispatch invokes the boundary exactly once
(test 21), evidence is recorded once with relative path + sha256 + size + format +
profile (tests 22–25), failed renders create no false success (test 26), and
idempotency/recovery hold (tests 27–29).

---

## 14. Changed Files

| File | Status | Purpose |
|------|--------|---------|
| `scos/control_center/hvs_render_dispatch.py` | added | Stage 5 implementation (render-request + identity, `HVSRenderDispatchApproval`, `RenderEvidenceLedger`/`RenderEvidenceRecord`, `HVSRenderExecutor`, public `dispatch_hvs_render`) |
| `scos/control_center/tests/test_hvs_render_dispatch.py` | added | 35 focused deterministic tests (full 35-point matrix) |
| `docs/certification/SCOS-HVS-integration-stage-5-render-dispatch-evidence.md` | added | this certification |

No modification to Stage 1–4 files. `create_hvs_project()`, `materialize_hvs_assets()`,
and the HVS renderer are unchanged. The only new production module is additive.

> Note: `scos/control_center/scos/work/stage7_closure_tests/closure.json` (untracked,
> pre-existing from the unrelated `test_stage7_closure_gate` suite) is **not** part
> of this stage and is intentionally excluded from the commit.

---

## 15. Known Limitations

- `created_at` in evidence records is the Stage 2 deterministic placeholder
  (`None`) — no wall-clock invented at any stage.
- Approval `expires_at` is only evaluated when an injectable `clock` is supplied.
- HVS fixes the output path per (project, fmt), so a changed preset for the same
  project requires a new HVS project (HVS no-overwrite); SCOS reports
  `render_identity_conflict` rather than overwriting.
- The real HVS render binary (`--fake-render` omitted) was not executed in this
  stage; the fake-render simulation stands in for the boundary contract.
- Full-suite collection still contains 24 pre-existing failures in unrelated
  legacy modules (§12).

---

## 16. Rollback

Stage 5 is additive (3 new files, no edits to existing modules). Rollback is a
single `git rm` of the three added files; no migration, no state in the real HVS
repo, and Stage 3/4 ledgers are unaffected.

---

## 17. Final Verdict

**PASS.** All in-scope gates are green: 35 focused Stage 5 tests pass (stable x2);
Stage 1–4 regression (140) passes; Control Center suite smoke-collectable (test_33);
full collectable Control Center suite (784 passed) with only 24 pre-existing
unrelated failures; HVS repo verified clean; security scan clean; dry-run and
safety/denial taxonomies proven; idempotency and recovery proven; evidence schema
validated.

**Recommendation (separate approval required — NOT begun):** Stage 6 — Render
Validation, Quality Gate, and Export-Ready Evidence.
