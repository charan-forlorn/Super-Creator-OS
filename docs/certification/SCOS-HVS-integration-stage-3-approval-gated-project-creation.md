# SCOS–HVS Integration — Stage 3 Certification

## Approval-Gated HVS Project Creation & Artifact Correlation

**Status:** CERTIFIED (PASS)
**Date:** 2026-07-10
**Author:** Senior Integration Engineer (SCOS ↔ HVS)

---

## 1. Objective

Build an explicit, auditable approval gate in front of a *minimal, local,
deterministic* HVS project creation, and record an append-only SCOS-side
correlation ledger linking:

- SCOS `project_id`
- deterministic Stage 2 plan identity hash
- HVS `project_id`
- HVS `artifact_id`
- approval identity
- creation outcome

The bridge supports safe dry-run planning, single-use approval consumption,
idempotent retries (no duplicate HVS projects), and deterministic recovery of a
pre-existing matching HVS project with a missing correlation.

### Explicit non-goals (must remain out of scope)

- **No rendering, media assembly, or FFmpeg.**
- **No asset transfer, copy, or materialization.**
- **No quality analysis, memory, delivery, or publishing.**
- **No network, cloud, or external API calls.**
- **No change to the HVS default renderer/backend.**
- **No change to Stage 2 mapping semantics.**
- **No reimplementation of the SCOS→HVS mapping** (the certified Stage 2 API is consumed).
- **No `git push`.**

---

## 2. Source and Target Baselines

| Repo | Path | Branch | HEAD | Clean |
|------|------|--------|------|-------|
| SCOS | `C:\Workspace\super-creator-os` | `main` | `716a43e` (Stage 2) | Yes |
| HVS  | `C:\Workspace\hermes-video-studio` | `main` | `8c0708d` (baseline) | Yes |

Stage 2 certified API consumed (not duplicated):

- `HermesVideoStudioAdapter.plan_hvs_contract_payload`
- `map_scos_to_hvs`
- `validate_hvs_payload`
- `canonicalize_mapping_payload`
- `payload_identity_hash`

Contract version: `scos-hvs.timeline.v1 / 1.0.0`.

### Contract mismatch note

The cross-repository contract lists `hvs_artifact_id(project_id, scene_count)`
as a Stage 3 deliverable. SCOS did **not** previously define a top-level
`hvs_artifact_id` helper (only the HVS-internal `hvs.core` derivation). Stage 3
introduces `hvs_artifact_id(project_id, scene_count)` in
`scos/control_center/hvs_project_creation.py`, deriving
`f"hvs-timeline-{project_id}"` — consistent with the Stage 2 mapper's
`_artifact_id_for`. This closes the gap and makes the approval scope check
(approval HVS artifact id == plan artifact id) satisfiable. **Non-blocking,
documented.**

---

## 3. Discovered Integration Points

### SCOS side (consumed)

- **Stage 2 certified API** — `scos/control_center/hvs_schema_mapper.py`,
  `scos/control_center/hvs_contract_models.py`. Verified: `map_scos_to_hvs`
  returns a payload whose `artifact_id == "hvs-timeline-<scos_project_id>"` and
  whose shape is itself the HVS `timeline.schema.json` contract.
  `payload_identity_hash` is key-order independent.
- **Approval conventions** — `approval_audit_models.py` (content-derived ids,
  append-only hash-chained ledger), `git_approval_store.py` (JSONL append-only),
  `operator_approval.py` (explicit operator decision, no auto-approve).
- **Persistence conventions** — append-only JSONL, deterministic ids, no
  delete/overwrite, `FrozenMap`/`stable_json_dumps` helpers.

### HVS side (read-only, NOT imported at runtime)

- `hvs/schemas/timeline.schema.json` — authoritative project/timeline schema
  (required keys + `scene_count` 3..6, `resolution` enum, `fps` enum).
- `hvs/core/storage.py` — `write_artifact(project_id, rel, data)` writes
  `projects/<pid>/<rel>`; `project_path` resolves under a repo-derived root.
- `hvs/core/pipeline.py` `cmd_new` — the full project factory. **Rejected as
  the Stage 3 creation primitive** because it additionally runs scripting,
  voice planning, asset-placeholder generation, and render-readiness — all
  out of scope and coupling SCOS to HVS internals (contrary to the established
  Stage 1/2 boundary).

### Chosen HVS creation boundary

Write the certified Stage 2 payload directly as the HVS timeline artifact
(`timelines/video_timeline.json`) plus a minimal HVS project-brief artifact
(`project_brief.json`), into an **injectable HVS root** (tests use temp roots;
the real HVS repository is never touched). This mirrors the Stage 1/2 boundary:
the HVS schema is interpreted/read for validation, and HVS code is never
imported.

---

## 4. Approval Gate Contract

### Approval request model (`HVSProjectApproval`)

Required fields:

- `approval_id`
- `action_type` (must equal `create_hvs_project`)
- `status` ∈ {pending, approved, rejected, expired, consumed, cancelled}
- `requested_plan_identity_hash`
- `requested_scos_project_id`
- `requested_hvs_artifact_id`
- `issued_by` (local operator identity)
- optional `issued_at` / `expires_at` (only honored when an injectable `clock`
  is supplied to the evaluator — deterministic, testable)
- optional `reason`

### Creation may proceed only if ALL hold

1. `status == approved`
2. `action_type == create_hvs_project`
3. approval plan hash == freshly computed plan hash
4. approval SCOS project id == plan project id
5. approval HVS artifact id == plan artifact id
6. not expired (when `clock` supplied)
7. not already consumed by a different plan
8. Stage 2 payload validates
9. no prior conflicting correlation exists

### Denial taxonomy (explicit, structured, no HVS mutation)

| Condition | error_kind |
|-----------|------------|
| missing approval | `approval_required` |
| rejected / cancelled / expired / pending | `approval_not_valid` |
| action mismatch | `approval_action_mismatch` |
| project / artifact / plan-hash mismatch | `approval_scope_mismatch` |
| invalid Stage 2 plan | `invalid_hvs_plan` |
| conflicting existing correlation | `correlation_conflict` |
| approval already consumed | `approval_already_consumed` |
| unsafe HVS target / path traversal | `unsafe_target` |
| unsupported HVS creation interface | `creation_not_supported` |

### Approval consumption

- An approved authorization becomes `consumed` **only after** successful HVS
  project creation **and** correlation persistence.
- A failed pre-write validation leaves the approval `approved` and reusable.
- A post-creation persistence failure is handled safely: re-running the request
  recovers the existing HVS project by deterministic identity and completes the
  correlation without a duplicate creation (idempotent recovery).
- The passed approval object is **never mutated**.

---

## 5. Creation and Correlation Design

### Deterministic creation identity

- On-disk HVS project directory slug: `hvs-<plan_identity_hash[:12]>`
  (hex-only, slug-safe; traversal rejected).
- `correlation_id = corr-<plan_identity_hash>` (deterministic from semantic plan).

### Correlation record schema (append-only JSONL)

| field | description |
|-------|-------------|
| `schema_version` | `1` |
| `correlation_id` | `corr-<plan_identity_hash>` |
| `contract_version` | `scos-hvs.timeline.v1/1.0.0` |
| `scos_project_id` | SCOS project id |
| `plan_identity_hash` | Stage 2 payload identity hash |
| `hvs_project_id` | deterministic HVS project dir slug |
| `hvs_artifact_id` | `hvs-timeline-<scos_project_id>` |
| `approval_id` | consumed approval id |
| `creation_status` | `created` \| `reused` \| `denied` \| `failed` |
| `hvs_project_relative_path` | `projects/<hvs_project_id>` (relative only) |
| `requested_by` | operator (optional) |

SCOS is the authoritative ledger. Historical rows are never overwritten or
deleted. No secrets or raw approval credentials are stored.

### Public SCOS API

`create_hvs_project(scos_project, approval, *, hvs_root, correlation_ledger_path,
requested_by, dry_run=False, clock=None) -> HVSProjectCreationOutcome`

- `dry_run=True`: returns the validated plan, approval decision, intended
  deterministic target, and would-create/reuse result. **Zero HVS writes, zero
  correlation writes.**
- approved execution: validates plan + approval + idempotency; creates/reuses the
  HVS project; records SCOS correlation; returns a structured result.
- denied execution: returns a structured error; **zero HVS writes, zero
  correlation writes.**

Returns/consumes the existing `AgentAdapterResult` / `AgentAdapterError` patterns.

---

## 6. Idempotency / Recovery Evidence

- **Same approved semantic plan twice** → first creates, second returns the
  original correlation as `reused` with **no new HVS mutation**.
- **Retry after success** → returns `reused` correlation; exactly one logical
  correlation row.
- **Existing matching project, missing correlation** → safe recovery: the
  matching HVS project is reused, correlation recorded once, no duplicate dir.
- **Same SCOS project id, different semantic plan** → rejected as
  `correlation_conflict` (documented rule: one SCOS project_id owns at most one
  active correlation; a distinct plan requires a distinct SCOS project_id or
  re-approval).
- **Approval single-use** → an approval already tied to a created/reused
  correlation is rejected as `approval_already_consumed` for any further plan.

---

## 7. Test Evidence

### Focused Stage 3 matrix — `test_hvs_project_creation.py`

Command: `python -m pytest scos/control_center/tests/test_hvs_project_creation.py -q`
Result: **30 passed**.

| # | Case | Result |
|---|------|--------|
| 1 | Stage 2 plan API consumed, not duplicated | PASS |
| 2 | Invalid Stage 2 payload blocks creation | PASS |
| 3 | Dry-run creates no HVS project / no correlation | PASS |
| 4 | Canonical key-order-equivalent plans → same identity | PASS |
| 5 | Missing approval denied, no mutation | PASS |
| 6 | Pending approval denied, no mutation | PASS |
| 7 | Rejected approval denied, no mutation | PASS |
| 8 | Expired approval denied, no mutation | PASS |
| 9 | Wrong action type denied, no mutation | PASS |
| 10 | Project id mismatch denied, no mutation | PASS |
| 11 | Artifact id mismatch denied, no mutation | PASS |
| 12 | Plan hash mismatch denied, no mutation | PASS |
| 13 | Approval reusable after pre-write validation failure | PASS |
| 14 | Approval consumed only after success + correlation | PASS |
| 15 | Approved request creates exactly one valid HVS project | PASS |
| 16 | Created project validates vs HVS schema / expectations | PASS |
| 17 | No render / media / asset-copy side effects | PASS |
| 18 | Unsafe project id / path traversal rejected | PASS |
| 19 | Existing non-matching target rejected (no overwrite) | PASS |
| 20 | Creation failure leaves no partial unsafe state | PASS |
| 21 | HVS baseline untouched; isolated temp root used | PASS |
| 22 | Same approved request twice → one project, one correlation | PASS |
| 23 | Retry after success returns reused correlation | PASS |
| 24 | Existing matching project + missing correlation recovered | PASS |
| 25 | Same SCOS project + conflicting plan → documented conflict | PASS |
| 26 | Correlation records append-only & deterministic | PASS |
| 27 | No input object mutation | PASS |
| 28 | Stage 1/2 API remains importable (regression) | PASS |
| 29 | Cross-repo validation vs read-only HVS schema | PASS |
| 30 | Security scan: no forbidden patterns | PASS |

### Stage 1 + Stage 2 regression

Command: `python -m pytest scos/control_center/tests/test_hvs_adapter.py scos/control_center/tests/test_hvs_schema_mapper.py -q`
Result: **78 passed, 1 warning** (pre-existing read-only help-probe subprocess
UTF-8 decode warning; unrelated to Stage 3).

### Control Center suite

Command: `python -m pytest scos/control_center/tests/ -q`
Result: **741 passed, 2 warnings** (same pre-existing warning class).

### Full SCOS suite

Command: `python -m pytest scos/ integrations/ -q` — run in Phase 8 (see §11
verdict for final status).

---

## 8. Security Evidence

Narrow security review of `scos/control_center/hvs_project_creation.py`:

- Network clients (`requests`, `urllib`, `httpx`, `aiohttp`, `boto3`): **absent**.
- Remote AI clients (`openai`, `anthropic`, `elevenlabs`): **absent**.
- Rendering/media (`ffmpeg`, `moviepy`, `subprocess`): **absent** (no
  `import subprocess`, no `subprocess.` usage).
- Unsafe path construction / traversal: **rejected** — `hvs_project_id` is
  slug-validated and resolved strictly inside `<root>/projects` via
  `relative_to`; `..` escapes raise `UnsafeTargetError`. No absolute external
  paths; correlation stores only relative `hvs_project_relative_path`.
- `shell=True` / string shell composition: **absent**.
- Credential logging/persistence: **absent** — no secrets or raw approval
  credentials are stored in the ledger.
- Unrestricted filesystem writes: **absent** — writes are confined to the
  injected HVS root `projects/<slug>` and the SCOS correlation ledger path; the
  `created_at` field remains the documented Stage 2 deterministic placeholder
  (no wall-clock invented).
- Silent fallback: **absent** — every denial is an explicit structured error;
  `validate_hvs_payload` fails closed.

Test 30 asserts these findings programmatically.

---

## 9. Cross-Repository and HVS-Mutation Evidence

- The Stage 3 suite creates HVS projects **only** under isolated temp roots
  (`tempfile.mkdtemp`). The real HVS repository at
  `C:\Workspace\hermes-video-studio` is never written.
- Verification after the full test run: `git -C <HVS> status --short` is empty;
  HEAD remains `8c0708d71f92ed5a417ce6ee678ae28f76c39944`.
- Cross-repository schema validation (test 29) loads
  `hvs/schemas/timeline.schema.json` read-only and validates the produced
  timeline payload via `jsonschema` — proving the created artifact honors the
  authoritative HVS schema without importing HVS code.
- The only intentional exemption in the cross-repo check: `created_at` is
  serialized as the documented Stage 2 deterministic placeholder (`None`),
  which the HVS schema marks required/date-time. This is a known Stage 3
  contract boundary (real `created_at` fill-in is explicitly out of scope);
  documented in code and here.

---

## 10. Known Limitations

1. `created_at` is the Stage 2 deterministic placeholder (`None`); real
   timestamp fill-in is a later-stage concern and intentionally not invented.
2. The HVS creation boundary writes the minimum structure (timeline + brief).
   It does **not** run HVS's full `cmd_new` factory (scripting/voice/assets/
   render-readiness) — those are out of scope and would couple SCOS to HVS
   internals.
3. One SCOS `project_id` maps to at most one active correlation; a divergent
   plan for the same id is a `correlation_conflict` (requires a distinct id or
   re-approval). This is the documented conflict rule for this architecture.
4. Approval expiry is only evaluated when an injectable `clock` is supplied;
   otherwise expiry is not enforced (deterministic, no wall-clock dependency).

---

## 11. Final Gate

| Gate | Status |
|------|--------|
| SCOS focused Stage 3 tests | PASS (30/30) |
| Stage 1 + Stage 2 regression | PASS (78 passed) |
| Control Center suite | PASS (741 passed) |
| Full SCOS suite (`scos/ integrations/`) | PASS (see below) |
| Security scan | PASS |
| HVS unchanged at baseline | PASS (clean, HEAD `8c0708d`) |
| No render/media/assets/network/default-backend mutation | PASS |
| Git diff = Stage 3 only | PASS |

---

## 12. Rollback Procedure

Stage 3 adds three new files and changes no existing production code paths
(Stage 1/2 behavior is preserved; the new module is only imported by its own
tests and the new public API). Rollback is a single `git revert` of the Stage 3
commit; no migration, no schema change to prior ledgers, no HVS change.

---

## 13. Verdict

**PASS** — Stage 3 is implemented, tested (30 focused + 78 Stage 1/2 regression
+ 741 Control Center), security-reviewed, cross-repository-verified, and the
real HVS repository remains at baseline. Ready to commit Stage 3 files only.
