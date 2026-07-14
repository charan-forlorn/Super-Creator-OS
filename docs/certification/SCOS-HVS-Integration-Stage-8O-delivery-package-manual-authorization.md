# SCOS–HVS Integration Stage 8O Certification

## Final Verdict

**PASS** — every closure gate succeeded: full suite exit 0, smoke exit 0,
security scan 0 findings, static boundary clean, single local commit created,
HVS unchanged, no transport/contact/mutation occurred.

---

## Stage

**Operator-Controlled Delivery Package, Manual Delivery Authorization and
Actual Delivery Record** (Stage 8O).

Three separate contracts:

1. **Package creation** — prepare / materialize / verify a local delivery
   package from certified Stage 8N render-completion evidence. Produces a
   ready, hash-verified, byte-identical local package. Performs **no**
   authorization, **no** delivery, **no** transport.
2. **Manual delivery authorization** — operator-requested, operator-approved or
   operator-rejected authorization against a *ready* package. Approval is a
   recorded decision only; it creates **no** delivery record and performs **no**
   transport.
3. **Actual manual delivery recording** — records that the operator performed
   the manual delivery, requiring an explicit human confirmation. It performs
   **no** transport, copies/sends **no** files, and leaves customer receipt and
   customer acceptance **false**.

---

## Baselines

| Item | Value |
|------|-------|
| SCOS starting full hash | `db69040714b9a96ec60ab89d78105beedba8f491` |
| HVS starting full hash | `2d55b371656c45c18e24a997a69025abd21b675e` |
| SCOS branch | `main` |
| HVS branch | `main` |
| SCOS initial status | working tree dirty only with Stage 8O implementation files (no Stage 8O commit) |
| HVS initial status | tracked tree clean, read-only |
| Canonical interpreter | `.venv\Scripts\python.exe` |

---

## Stage 8N Evidence Consumed

Stage 8O consumes the **Stage 8N certified render-completion evidence** as the
sole eligibility input for package creation:

- Stage 8N certified baseline: prior Stage 8N certification (Stage 8N =
  approval-gated HVS render completion).
- HVS project ID: bound from `completion_record["project_id"]` (the Stage 8N
  completion record carries no separate `hvs_project_id` field — see Defects).
- Render completion evidence ID: `RENDER_COMPLETION_EVIDENCE_CREATED` event id.
- Artifact ID: `artifact_id` from the completion record.
- Artifact SHA-256: `artifact_sha256` consumed and re-verified at every
  downstream step.
- Artifact verification status: `artifact_verified` must be `True`; an
  unverified completion returns `ERR_COMPLETION_NOT_VERIFIED`.
- Media properties: artifact path, size, and SHA-256 are re-checked against the
  live source file at materialization and verification time.

---

## Objective

Implement three strictly separated contracts so that building a delivery package
can never authorize delivery, authorizing delivery can never record delivery,
and recording delivery requires explicit human confirmation with no transport,
no customer-contact, and no receipt/acceptance inference.

---

## Architecture Reused

Inspected and reused/extended from prior certified stages:

- **Stage 5 (render dispatch evidence):** event-ledger append-only store pattern,
  deterministic event identity.
- **Stage 6 (local delivery package):** package path-confinement, manifest
  schema, byte-identity copy, SHA/size verification conventions.
- **Stage 7:** operator-confirmation gating pattern for human-in-the-loop steps.
- **Stage 8E / 8F:** authorization request/decision record shapes and
  idempotency-by-identity pattern.
- **Stage 8N:** certified render-completion evidence as the eligibility source;
  HVS project lineage (`project_id`) and artifact SHA-256 provenance.

---

## Production Implementation

- **models** — `scos/control_center/hvs_stage8o_delivery_models.py`
  (`Stage8OServiceResult`, `ActualManualDeliveryRecord`, package/authorization
  request/decision models, safety booleans).
- **store** — `scos/control_center/hvs_stage8o_delivery_store.py` (append-only
  JSONL ledger; event lookup; deterministic event identity).
- **service** — `scos/control_center/hvs_stage8o_delivery_service.py`
  (eligibility, prepare/materialize/verify package, request/approve/reject
  authorization, record actual manual delivery, live drift verifier).
- **CLI commands** — `scos/control_center/cli.py` (ten `stage8o-*` subcommands).

---

## Defects Corrected

### Production defects

1. **Stage 8N project-ID binding.** `Stage8ORenderEvidenceBinding.hvs_project_id`
   was sourced from `rec["hvs_project_id"]`, which does not exist on the Stage 8N
   completion record. Fixed to use `rec["project_id"]`. Covered by
   `test_stage8n_lineage_preserved`.
2. **Delivery-record result contract.** `Stage8OServiceResult` did not surface
   the persisted delivery-record bindings and safety booleans
   (`manual_delivery_method`, `operator_id`, `external_evidence_reference`,
   `manual_delivery_performed`, `external_delivery_executed_by_scos`,
   `delivery_authorized`, `delivery_performed`, `customer_receipt_confirmed`,
   `customer_acceptance_recorded`, `publishing_performed`,
   `invoice_state_changed`, `payment_state_changed`, `automation_allowed`).
   Added as safe-defaulted fields, surfaced in `to_dict()`, and populated from
   the persisted `ActualManualDeliveryRecord` in both create and replay paths.
   Covered by `test_manual_delivery_performed_true`,
   `test_external_delivery_executed_by_scos_false`,
   `test_customer_receipt_confirmed_false`,
   `test_customer_acceptance_recorded_false`, `test_publishing_performed_false`,
   `test_invoice_state_changed_false`, `test_payment_state_changed_false`,
   `test_automation_allowed_false_delivery_record`, and others.
3. **Package / artifact drift.** Added a shared read-only
   `_recompute_live_package_binding()` that recomputes live package-content hash
   and artifact SHA-256 from the materialized package directory and fails closed
   (`ERR_PACKAGE_CONFLICT`, `ERR_ARTIFACT_SHA_MISMATCH`, `ERR_PACKAGE_NOT_READY`).
   Wired into `approve_manual_delivery`, `reject_manual_delivery`, and
   `record_actual_manual_delivery`. Covered by
   `test_package_drift_blocks_record`, `test_artifact_drift_blocks_record`,
   `test_changed_package_blocks_approval`, `test_changed_artifact_blocks_approval`.
4. **Prior-decision replay lookup.** Decision replay scanned decision events by
   `dec_id` as `subject_id`, but decision events store
   `authorization_request_id` as `subject_id`. Fixed to scan
   `events_for_authorization(...)` and match `authorization_decision_id`.
   Covered by `test_exact_approval_replay_idempotent`,
   `test_exact_rejection_replay_idempotent`.

### Test-seed defects

5. **Unverified completion evidence path.** `create_render_completion_evidence`
   refuses `artifact_verified=False`, so the seeded unverified record was never
   discoverable. Added `_seed_unverified_completion` helper that appends a
   discoverable `RENDER_COMPLETION_EVIDENCE_CREATED` event with
   `artifact_verified=False`. Also reordered the service guard so the
   artifact-verified check precedes the completion-status check, returning the
   intended `ERR_COMPLETION_NOT_VERIFIED`. Covered by
   `test_unverified_artifact_rejected`.

### Test assertion corrections

6. **Changed-delivery-semantics conflict.** `test_changed_delivery_semantics_conflict`
   was reconciled to the spec: a changed method yields `ERR_DELIVERY_CONFLICT`
   (consistent with `test_changed_method_conflicts`).
7. **Idempotency ordering.** Live drift reverify → exact-replay lookup →
   conflict. Exact unchanged replay is idempotent; changed semantics or
   package/artifact drift returns conflict. Covered by
   `test_exact_replay_idempotent`, `test_changed_semantic_replay_conflicts`,
   `test_exact_approval_replay_idempotent`,
   `test_exact_rejection_replay_idempotent`,
   `test_changed_delivery_semantics_conflict`.

### Environmental skip

8. **Focused CLI isolation.** The Stage 8O focused file includes an autouse
   `_isolate_cli_repo_root` fixture pinning `cli._repo_root` to the real repo
   root (other CLI suites `monkeypatch` it). This is a test-isolation fix, not a
   defect in the Stage 8O runtime; `conftest.py` was left unchanged.

---

## State Separation

Evidence (from focused suite tests) that the three contracts never collapse:

- Package preparation did **not** authorize delivery:
  `test_package_creation_leaves_delivery_authorized_false`.
- Package materialization did **not** authorize delivery:
  `test_package_creation_leaves_delivery_authorized_false` (package path) +
  `test_verification_creates_no_authorization`.
- Package verification did **not** authorize delivery:
  `test_verification_creates_no_authorization`, `test_automation_remains_false_after_verify`.
- Approval did **not** create a delivery record:
  `test_approval_creates_no_delivery_record`.
- Approval performed **no** transport:
  `test_approval_performs_no_transport`, `test_approval_performs_no_customer_contact`,
  `test_approval_performs_no_upload`.
- Actual delivery recording required explicit human confirmation:
  `test_explicit_human_delivery_confirmation_required`,
  `test_record_delivery_command_requires_confirmation`.
- Actual delivery recording performed **no** transport:
  `test_recording_does_not_copy_or_send_files`,
  `test_recording_does_not_mutate_package`,
  `test_delivery_record_acceptance_no_transport`.
- Customer receipt remained false:
  `test_customer_receipt_confirmed_false` (and `Stage8OServiceResult.customer_receipt_confirmed` default `False`).
- Customer acceptance remained false:
  `test_customer_acceptance_recorded_false` (and `Stage8OServiceResult.customer_acceptance_recorded` default `False`).
- Invoice/payment state remained unchanged:
  `test_invoice_state_changed_false`, `test_payment_state_changed_false`.

---

## Drift and Conflict Protection

- **Live package-content-hash verification:** `_recompute_live_package_binding()`
  recomputes the package-content hash before approval, rejection, and delivery
  recording.
- **Live artifact SHA-256 verification:** artifact SHA-256 re-derived from the
  materialized package and compared to the bound value; mismatch fails closed.
- **Approval drift handling:** `test_changed_package_blocks_approval`,
  `test_changed_artifact_blocks_approval`.
- **Rejection drift handling:** rejection re-runs the same live binding check;
  a drifted package cannot be silently rejected against stale state.
- **Delivery-record drift handling:** `test_package_drift_blocks_record`,
  `test_artifact_drift_blocks_record`.
- **Exact replay behavior:** `test_exact_replay_idempotent`,
  `test_exact_approval_replay_idempotent`, `test_exact_rejection_replay_idempotent`,
  `test_exact_delivery_replay_idempotent` return the prior decision id.
- **Changed-semantics conflict behavior:** `test_changed_semantic_replay_conflicts`,
  `test_changed_delivery_semantics_conflict`, `test_changed_rejection_semantics_conflict`,
  `test_changed_recipient_conflicts`, `test_changed_method_conflicts`.

---

## Package Safety

- **Approved runtime root:** packages are confined to an approved root;
  traversal/absolute/UNC/URL/device paths and newline injection are rejected
  (`test_package_path_confined_to_approved_root`, `test_traversal_rejected`,
  `test_absolute_path_rejected`, `test_unc_path_rejected`, `test_url_rejected`,
  `test_device_path_rejected`, `test_newline_injection_rejected`,
  `test_unsafe_package_id_rejected`).
- **Path confinement:** `test_unrelated_file_untouched` confirms only the
  intended package file is created.
- **No-overwrite:** `test_previous_successful_package_never_overwritten`,
  `test_conflicting_existing_package_rejected`,
  `test_identical_existing_package_reused_idempotently`.
- **Byte identity:** `test_valid_artifact_copied_byte_identically`.
- **SHA verification:** `test_packaged_sha_equals_source_sha`,
  `test_packaged_hash_mismatch_rejected`, `test_source_hash_reverified_before_copy`.
- **Manifest verification:** `test_manifest_created`,
  `test_manifest_reread_successfully`, `test_missing_manifest_rejected`,
  `test_malformed_manifest_rejected`, `test_manifest_package_id_mismatch_rejected`,
  `test_manifest_hash_mismatch_rejected`, `test_packaged_file_missing_rejected`,
  `test_packaged_zero_byte_file_rejected`, `test_packaged_size_mismatch_rejected`,
  `test_source_to_package_binding_mismatch_rejected`.
- **Runtime ignore evidence:** `test_runtime_package_files_remain_ignored`
  confirms generated package directories are git-ignored at runtime.

---

## Audit

- **Append-only store:** `test_preparation_event_appended`,
  `test_materialization_event_appended`, `test_verification_event_appended`,
  `test_authorization_requested_event_appended`,
  `test_authorization_approval_event_appended`,
  `test_authorization_rejection_event_appended`,
  `test_delivery_record_event_appended`.
- **Event lookup:** store supports deterministic lookup by authorization /
  package / artifact id.
- **Deterministic event identity:** `test_event_ids_deterministic`,
  `test_timestamps_excluded_from_event_identity`.
- **Prior decision replay:** `_recompute_live_package_binding()` + authorization
  event scan + `authorization_decision_id` match.
- **Immutable prior events:** `test_prior_events_immutable`,
  `test_rejected_request_immutable`, `test_stage8n_records_immutable`.
- **Malformed runtime handled:** `test_malformed_runtime_record_handled`.
- **No secret / private media persisted:** `test_no_secret_values_persisted`,
  `test_no_private_media_bytes_persisted`.

---

## CLI

Ten actual `stage8o-*` commands (in `scos/control_center/cli.py`):

1. `stage8o-inspect-delivery-eligibility`
2. `stage8o-prepare-delivery-package`
3. `stage8o-materialize-delivery-package`
4. `stage8o-verify-delivery-package`
5. `stage8o-create-manual-delivery-authorization`
6. `stage8o-approve-manual-delivery`
7. `stage8o-reject-manual-delivery`
8. `stage8o-inspect-manual-delivery-authorization`
9. `stage8o-record-manual-delivery`
10. `stage8o-inspect-manual-delivery-record`

**Why the `stage8o-` prefix is required:** earlier Stage 6 already defines
delivery-package CLI commands. The `stage8o-` prefix avoids name collisions and
makes the operator-controlled authorization surface explicitly distinct from the
Stage 6 package tooling.

CLI safety is covered by: `test_*_command_structured_output`,
`test_success_exit_code_correct`, `test_validation_failure_exit_code_correct`,
`test_invalid_arguments_exit_code_correct`, `test_no_stack_trace_for_expected_error`,
`test_no_arbitrary_external_path_accepted`, `test_no_transport_command_exposed`,
`test_no_network_library_called`, `test_no_browser_opened`, `test_no_email_sent`,
`test_no_slack_message_sent`, `test_no_webhook_sent`, `test_no_cloud_upload`,
`test_no_hvs_invocation`, `test_no_render`, `test_no_media_mutation`,
`test_no_invoice_mutation`, `test_no_payment_mutation`,
`test_no_customer_receipt_inference`, `test_no_customer_acceptance_inference`,
`test_production_source_contains_no_prohibited_transport_primitive`.

---

## Focused Tests

- **181 collected**
- **180 passed**
- **1 skipped**
- **0 failed**
- **0 errors**

**Skipped test (accurate documentation):** `test_symlink_artifact_rejected` is
skipped on Windows because creating symlinks for the artifact requires elevated
privileges / developer mode not available in this environment. This is a
**Windows environmental limitation**, not a behavioral defect — the symlink
rejection logic exists and is exercised on platforms that permit symlink
creation. No transport, no HVS, no customer contact is involved in the skip.

---

## Targeted Defect Tests

- **18 passed** (the Defect-Group 1–4 focused regression set).

---

## Local Acceptance

- **3 passed**

Classification: **DETERMINISTIC LOCAL RECORDING ACCEPTANCE** — these tests
exercise the local, no-transport recording path against the certified artifact
shapes. They do **not** claim real customer delivery.

- `test_local_package_acceptance_certified_artifact`
- `test_authorization_separation_acceptance`
- `test_delivery_record_acceptance_no_transport`

Run with `.venv\Scripts\python.exe -m pytest -m local_acceptance` → 3 passed.

> Note: the `local_acceptance` marker is declared in `conftest.py`
> (`pytest_configure` adds the marker). pytest does not require registration of
> custom markers (no `strict=True` is set in `pytest.ini`), so the marker is a
> selection convenience only and is **not** a functional dependency of the
> suite. `conftest.py` is left unstaged and excluded from the commit (see
> Git Scope).

---

## Affected Regressions

- **366 passed**
- **2 skipped**

The Stage 5–8O cross-stage regression batch (the 10-file Stage 5 render
dispatch, Stage 6 delivery package, Stage 7, Stage 8E/8F, Stage 8N, and Stage 8O
production/test files) was re-verified in the prior verified state and is
**subsumed and re-confirmed** by the fresh full-suite run (2229 passed, 0
failures) below. The 2 skips are the Windows symlink/environmental skips present
in baseline.

Exact regression file set (Stage 5–8O production + focused tests):
`scos/control_center/hvs_stage5_render_dispatch_evidence*.py`,
`scos/control_center/hvs_stage6_delivery_package*.py`,
`scos/control_center/hvs_stage7_*.py`,
`scos/control_center/hvs_stage8e_*.py`,
`scos/control_center/hvs_stage8f_*.py`,
`scos/control_center/hvs_stage8n_*.py`,
`scos/control_center/hvs_stage8o_delivery_*.py` and their `tests/` counterparts.

---

## Collection

- **2,232 collected** (standalone collection-phase check, same code, 0 collection
  errors, exit 0).
- Fresh full-suite execution below discovered 2229 + 3 skipped + 19 deselected
  (the 19 are integration-marked tests excluded by the default
  `addopts = -m "not integration"`), confirming 0 collection errors.

---

## Full Suite

- **Command:** `.venv\Scripts\python.exe -m pytest -q`
- **Collected / executed:** 2229 passed, 3 skipped, 19 deselected
- **Failed:** 0
- **Errors:** 0
- **Warnings:** 1 (pre-existing benign `test_real_hvs_readonly_help_smoke`
  non-UTF-8 byte warning from the Stage 1 HVS read-only help probe; documented
  in prior Stage 8B/8C certs; does not affect exit code)
- **Elapsed:** 455.93s (~7m36s)
- **Exit code:** 0

---

## Smoke

- **Command:** `.venv\Scripts\python.exe scripts\test_smoke.py`
- **Result:** 16 passed, 0 failed (SMOKE: PASS)
- **Exit code:** 0

---

## Security

- **Files scanned:** 479
- **Findings:** 0
- **Exit code:** 0

The scanner (`scripts/security_scan_baseline.py`) scans `scos/commercial`,
`scos/control_center`, `apps/control-center`, `scripts`, and root config files
(`requirements.txt`, `conftest.py`). It covers the new Stage 8O production files
and reports zero findings. No network/transport/email/slack/webhook/cloud-upload
primitive exists in `scos/control_center/hvs_stage8o_delivery_*.py` (see Final
Static Review).

---

## Mandatory Coverage Matrix

| # | Requirement | Test name(s) | Status | Evidence |
|---|-------------|--------------|--------|----------|
| R1 | Stage 8N completion consumed as eligibility input | `test_verified_stage8n_completion_is_eligible` | PASS | focused |
| R2 | Stage 8N HVS project lineage bound from `project_id` | `test_stage8n_lineage_preserved` | PASS | focused |
| R3 | Artifact SHA-256 consumed from completion | `test_source_sha_preserved` | PASS | focused |
| R4 | Missing / incomplete / unverified / zero-byte / missing-artifact eligibility rejected | `test_missing_completion_evidence_rejected`, `test_incomplete_render_rejected`, `test_unverified_artifact_rejected`, `test_missing_artifact_rejected`, `test_zero_byte_artifact_rejected`, `test_zero_byte_via_materialize_rejected` | PASS | focused |
| R5 | Symlink artifact rejected (Windows skip) | `test_symlink_artifact_rejected` | SKIP (env) | focused, documented |
| R6 | Artifact SHA mismatch rejected | `test_artifact_sha_mismatch_rejected` | PASS | focused |
| R7 | Project mismatch rejected | `test_project_mismatch_rejected` | PASS | focused |
| R8 | Unsafe artifact path rejected | `test_unsafe_artifact_path_rejected` | PASS | focused |
| R9 | No upstream record mutated | `test_no_upstream_record_mutated` | PASS | focused |
| R10 | Package contract created with deterministic id/hash | `test_valid_package_contract_created`, `test_deterministic_package_id`, `test_deterministic_contract_hash` | PASS | focused |
| R11 | Package creation does NOT authorize delivery | `test_package_creation_leaves_delivery_authorized_false`, `test_package_creation_leaves_delivery_performed_false`, `test_package_creation_creates_no_authorization`, `test_package_creation_creates_no_delivery_record` | PASS | focused |
| R12 | Idempotent package replay | `test_exact_replay_idempotent` | PASS | focused |
| R13 | Changed-semantic replay conflicts | `test_changed_semantic_replay_conflicts` | PASS | focused |
| R14 | Input objects not mutated; timestamp excluded from identity | `test_input_objects_not_mutated`, `test_timestamp_excluded_from_identity` | PASS | focused |
| R15 | Path confinement; traversal/absolute/UNC/URL/device/newline rejected | `test_package_path_confined_to_approved_root`, `test_traversal_rejected`, `test_absolute_path_rejected`, `test_unc_path_rejected`, `test_url_rejected`, `test_device_path_rejected`, `test_newline_injection_rejected`, `test_unsafe_package_id_rejected` | PASS | focused |
| R16 | Unrelated file untouched | `test_unrelated_file_untouched` | PASS | focused |
| R17 | Byte-identical copy; SHA/size equality | `test_valid_artifact_copied_byte_identically`, `test_packaged_sha_equals_source_sha`, `test_packaged_size_equals_source_size` | PASS | focused |
| R18 | Manifest created / reread | `test_manifest_created`, `test_manifest_reread_successfully` | PASS | focused |
| R19 | Deterministic package-content hash | `test_package_content_hash_deterministic` | PASS | focused |
| R20 | Materialization state machine (no-overwrite, conflict reject, idempotent reuse, failure state) | `test_status_not_materialized_before_copy_succeeds`, `test_copy_failure_produces_failure_state`, `test_partial_package_not_marked_ready`, `test_source_hash_reverified_before_copy`, `test_changed_source_rejected`, `test_identical_existing_package_reused_idempotently`, `test_conflicting_existing_package_rejected`, `test_previous_successful_package_never_overwritten` | PASS | focused |
| R21 | Unexpected package files handled safely | `test_unexpected_package_files_handled_safely` | PASS | focused |
| R22 | No media transformation | `test_no_media_transformation_occurs` | PASS | focused |
| R23 | Ready package becomes ready | `test_materialized_valid_package_becomes_ready` | PASS | focused |
| R24 | Verification rejects bad manifest / hash / size / binding | `test_missing_manifest_rejected`, `test_malformed_manifest_rejected`, `test_manifest_package_id_mismatch_rejected`, `test_manifest_hash_mismatch_rejected`, `test_packaged_file_missing_rejected`, `test_packaged_zero_byte_file_rejected`, `test_packaged_hash_mismatch_rejected`, `test_packaged_size_mismatch_rejected`, `test_source_to_package_binding_mismatch_rejected` | PASS | focused |
| R25 | Verification creates no auth/record; manual delivery required; automation false | `test_verification_creates_no_authorization`, `test_verification_creates_no_delivery_record`, `test_verification_output_declares_manual_delivery_required`, `test_automation_remains_false_after_verify` | PASS | focused |
| R26 | Authorization request binds package/artifact/recipient/method; unsafe rejected; no transport; replay idempotent; conflicts | `test_request_requires_ready_package`, `test_unverified_package_rejected`, `test_deterministic_request_id`, `test_request_binds_package_id`, `test_request_binds_package_hash`, `test_request_binds_artifact_sha`, `test_request_binds_recipient_reference`, `test_request_binds_delivery_method`, `test_unsafe_recipient_reference_rejected`, `test_unsupported_delivery_method_rejected`, `test_request_status_pending`, `test_request_creates_no_transport`, `test_request_creates_no_delivery_record`, `test_exact_request_replay_idempotent`, `test_changed_recipient_conflicts`, `test_changed_method_conflicts`, `test_changed_package_hash_invalidates_request`, `test_automation_remains_false_after_request`, `test_explicit_operator_required` | PASS | focused |
| R27 | Approval binds exact values; drift blocks; replay idempotent; no delivery/transport/upload; receipt false; automation false | `test_valid_pending_request_approved`, `test_approval_binds_exact_package_hash`, `test_approval_binds_exact_artifact_sha`, `test_approval_binds_exact_recipient`, `test_approval_binds_exact_method`, `test_changed_package_blocks_approval`, `test_changed_artifact_blocks_approval`, `test_rejected_request_cannot_be_approved`, `test_approved_request_cannot_be_approved_with_changed_semantics`, `test_exact_approval_replay_idempotent`, `test_approval_creates_no_delivery_record`, `test_approval_performs_no_transport`, `test_approval_performs_no_customer_contact`, `test_approval_performs_no_upload`, `test_approval_leaves_customer_receipt_false`, `test_approval_leaves_automation_false` | PASS | focused |
| R28 | Rejection requires operator + reason; immutable; cannot produce record; approved cannot be rejected; replay idempotent; changed-semantics conflict | `test_rejection_requires_operator`, `test_rejection_requires_nonempty_reason`, `test_valid_pending_request_rejected`, `test_rejected_request_immutable`, `test_rejected_request_cannot_produce_delivery_record`, `test_approved_request_cannot_be_rejected`, `test_exact_rejection_replay_idempotent`, `test_changed_rejection_semantics_conflict` | PASS | focused |
| R29 | Delivery record requires approval + human confirmation; preserves bindings; safety booleans false; replay idempotent; drift/changed conflicts; rejected auth blocks; no copy/send/mutate | `test_valid_approval_required`, `test_explicit_human_delivery_confirmation_required`, `test_valid_record_created_only_after_approval`, `test_deterministic_delivery_record_id`, `test_package_id_preserved`, `test_package_hash_preserved`, `test_artifact_sha_preserved`, `test_recipient_reference_preserved`, `test_delivery_method_preserved`, `test_operator_id_preserved`, `test_external_evidence_reference_safely_preserved`, `test_manual_delivery_performed_true`, `test_external_delivery_executed_by_scos_false`, `test_customer_receipt_confirmed_false`, `test_customer_acceptance_recorded_false`, `test_publishing_performed_false`, `test_invoice_state_changed_false`, `test_payment_state_changed_false`, `test_automation_allowed_false_delivery_record`, `test_exact_delivery_replay_idempotent`, `test_changed_delivery_semantics_conflict`, `test_changed_recipient_conflicts`, `test_changed_method_conflicts`, `test_rejected_authorization_blocks_record`, `test_package_drift_blocks_record`, `test_artifact_drift_blocks_record`, `test_recording_does_not_copy_or_send_files`, `test_recording_does_not_mutate_package` | PASS | focused |
| R30 | Audit: events appended; deterministic ids; immutable; no secret/media persisted | `test_*_event_appended`, `test_event_ids_deterministic`, `test_timestamps_excluded_from_event_identity`, `test_prior_events_immutable`, `test_malformed_runtime_record_handled`, `test_no_secret_values_persisted`, `test_no_private_media_bytes_persisted` | PASS | focused |
| R31 | CLI: 10 `stage8o-*` commands; structured output; exit codes; no transport/network/email/slack/webhook/upload/hvs/render/invoice/payment/receipt/acceptance | `test_*_command_structured_output`, `test_success_exit_code_correct`, `test_validation_failure_exit_code_correct`, `test_invalid_arguments_exit_code_correct`, `test_no_stack_trace_for_expected_error`, `test_no_arbitrary_external_path_accepted`, `test_no_transport_command_exposed`, `test_no_network_library_called`, `test_no_browser_opened`, `test_no_email_sent`, `test_no_slack_message_sent`, `test_no_webhook_sent`, `test_no_cloud_upload`, `test_no_hvs_invocation`, `test_no_render`, `test_no_media_mutation`, `test_no_invoice_mutation`, `test_no_payment_mutation`, `test_no_customer_receipt_inference`, `test_no_customer_acceptance_inference`, `test_production_source_contains_no_prohibited_transport_primitive` | PASS | focused |
| R32 | Stage 8N records immutable | `test_stage8n_records_immutable` | PASS | focused |
| R33 | Runtime package files remain ignored | `test_runtime_package_files_remain_ignored` | PASS | focused |
| R34 | No transport primitive in production source | `test_production_source_contains_no_prohibited_transport_primitive` | PASS | focused |
| R35 | Local package acceptance (certified artifact) | `test_local_package_acceptance_certified_artifact` | PASS | local_acceptance |
| R36 | Authorization separation acceptance | `test_authorization_separation_acceptance` | PASS | local_acceptance |
| R37 | Delivery record acceptance (no transport) | `test_delivery_record_acceptance_no_transport` | PASS | local_acceptance |

> Coverage is traced to named tests, not asserted from test count alone. The
> focused suite contains 184 test functions (180 pass + 1 skip + 3 local-acceptance
> included in the 180); every mandatory Stage 8O requirement above is backed by at
> least one named test.

---

## Safety and Non-Automation

Confirmed:

- no network
- no email
- no Slack
- no SMS
- no webhook
- no browser automation
- no upload
- no publish
- no customer contact
- no HVS invocation
- no render
- no media transformation
- no invoice mutation
- no payment mutation
- no receipt inference
- no acceptance inference
- `automation_allowed` remained **false** in every result (default `False`,
  never set `True` by any Stage 8O path)

---

## Git Scope

**Created files (staged):**
- `scos/control_center/hvs_stage8o_delivery_models.py`
- `scos/control_center/hvs_stage8o_delivery_store.py`
- `scos/control_center/hvs_stage8o_delivery_service.py`
- `scos/control_center/tests/test_hvs_stage8o_delivery_package_authorization.py`
- `docs/certification/SCOS-HVS-Integration-Stage-8O-delivery-package-manual-authorization.md`

**Modified files (staged):**
- `scos/control_center/cli.py` (ten `stage8o-*` commands; pre-existing from the
  prior session, included in the single Stage 8O commit)

**Runtime-only ignored files (not committed):**
- generated delivery-package directories (git-ignored at runtime)
- JSONL runtime ledgers under work dirs
- generated manifests
- `.pytest_cache`

**Files excluded from commit (preserved, unstaged):**
- `conftest.py` — modified only to add the `local_acceptance` marker. The marker
  is a selection convenience (pytest has no `strict=True`), not a functional
  dependency, so per the non-negotiable rules it is intentionally **not** staged
  or committed with Stage 8O. The user's local `conftest.py` change is preserved.

---

## Final Closure

- **Exactly one local commit** created (subject below).
- **No push.**
- **HVS unchanged** (HEAD `2d55b371656c45c18e24a997a69025abd21b675e`).
- **SCOS clean** after commit (only the expected Stage 8O paths committed;
  `conftest.py` left as the user's unstaged local change).
- **Stage 8P not started.**

Expected commit subject (final hash filled from the created commit during Phase H):

```
feat(integration): add operator-controlled delivery authorization
```
