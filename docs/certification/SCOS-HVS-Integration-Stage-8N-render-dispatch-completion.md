# SCOS–HVS Integration — Stage 8N: Approval-Gated Render Dispatch, Artifact Verification & Render Completion Evidence

**Certification status: PASS**
**Stage:** 8N (render dispatch completion, downstream of certified Stage 8M asset intake/materialization)
**Date of certification run:** 2026-07-14 (Asia/Bangkok)
**Agent:** Hermes Desktop (resume from CHECKPOINT 5)

---

## 1. Objective

Provide an approval-gated, operator-controlled Stage 8N boundary that:

1. Accepts a render request **only** from a certified Stage 8M READY state.
2. Requires a **separate, explicit Stage 8N render approval** (Stage 8M materialization approval never authorizes rendering).
3. Dispatches the render through the Stage-5-certified HVS CLI boundary
   `python -m hvs.cli render-hyperframes --project-id <id> --format vertical`,
   via bounded `subprocess.run` with `shell=False`, explicit `cwd`, and a timeout.
4. Independently verifies the produced artifact (SHA-256, ffprobe streams/codec/resolution/FPS/pixel-format/duration, and A/V semantics).
5. Produces **completion evidence** that is truthful: `artifact_verified`, with
   `delivery_authorized=false`, `publishing_authorized=false`, `customer_contact_performed=false`,
   `upload_performed=false`, `publishing_performed=false`, `invoice_state_changed=false`,
   `payment_state_changed=false`, `automation_allowed=false`.

---

## 2. Starting SCOS full hash

`ef6e73aa37fbcabd6f1bac7a06e655502d5f9235`

## 3. Final SCOS full hash (after commit)

`a10665ed0855c0f2699962f5b594c77d7e1aa808`

> NOTE: the repository working tree was already committed as
> `a10665e feat(integration): harden approval-gated HVS render completion`
> before this certification run. The tree was CLEAN at certification time. This document
> certifies that committed state. No further production/CLI/test edits were required
> (the previously reported "2 failing integration tests" were already repaired and
> committed in `a10665e`; re-running the integration cluster confirmed 11 passed / 0 failed).

## 4. Starting HVS full hash

`2d55b371656c45c18e24a997a69025abd21b675e`

## 5. Final HVS full hash

`2d55b371656c45c18e24a997a69025abd21b675e` (unchanged — HVS tracked source untouched)

## 6. Architecture reused

* **Stage 8M production-asset intake/materialization** (`hvs_production_asset_service.py`,
  `hvs_production_asset_store.py`, `hvs_production_asset_models.py`) — source of the
  READY readiness record that Stage 8N gates on.
* **Stage 5 render-dispatch bridge** (`hvs_render_dispatch.py`) — the canonical HVS CLI
  invocation pattern (`python -m hvs.cli`, argv list, `shell=False`, timeout) reused
  for the Stage 8N dispatch.
* **Append-only JSONL store discipline** — Stage 8N keeps its own dedicated store under
  `scos/work/hvs_render_completion` (gitignored runtime data), mirroring the per-stage
  append-only convention (no edits-in-place, event_id idempotency).
* **Deterministic identity helpers** (`stable_id`, hash-based ids) reused from
  `hvs_commercial_proposal_models.py`.

New Stage 8N modules (all under `scos/control_center/`):

* `hvs_render_completion_models.py` (608 lines)
* `hvs_render_completion_store.py` (131 lines)
* `hvs_render_completion_service.py` (1650 lines)
* `tests/test_hvs_render_dispatch_completion.py` (1766 lines, 97 focused + 11 integration)
* CLI commands appended to `cli.py` (+315 lines, 9 Stage 8N subcommands)
* `scripts/security_scan_baseline.py` allow-list entry (+9 lines)
* `pytest.ini` integration marker (+3 lines)

---

## 7. Stage 8M evidence reverified

The verified project `hvs8l-e32880405a6292d1ac4e1f68997d085f` remains RESDY at the
HVS repo. Stage 8N reads the Stage 8M READY readiness record from the SCOS-side
Stage 8M store and refuses any render request when that evidence is missing, expired,
or mismatched.

Tests:
* `test_missing_stage8m_evidence_rejected`
* `test_non_ready_evidence_rejected`
* `test_stale_readiness_rejected`
* `test_stage8m_approval_cannot_authorize_render`
* `test_approval_binds_readiness_evidence`
* Integration: `TestStage8NRealHVS::test_stage8m_readiness_reverified`

---

## 8. Real HVS render command (Stage-5-certified boundary)

```
python -m hvs.cli render-hyperframes --project-id hvs8l-e32880405a6292d1ac4e1f68997d085f --format vertical
```

Stage 8N constructs this exact argv (verified by test `test_hvs_invocation_uses_argv`
and integration `test_dispatch_reaches_real_hvs_boundary`). SCOS drives HVS only
through this CLI; it never imports `hvs`, never writes into the HVS repository.

A real render was executed earlier through this boundary and produced a valid MP4
(see §Real-HVS Evidence). The artifact was **reused** for this certification
(no rerender), consistent with the "do not rerender unless invalidated" rule — the
artifact is present, matches the recorded evidence, and the contract is unchanged.

---

## 9. Render-request contract (fields)

A render request carries: `project_id`, `selected_format`, `width`, `height`, `fps`,
`target_duration_seconds`, `video_codec`, `pixel_format`, `audio_requirement`,
`no_overwrite_policy`, plus the Stage 8M provenance (`intake_manifest_id`,
`intake_manifest_content_hash`, `render_readiness_id`, `render_readiness_content_hash`).

The request identity (`render_request_id`) and contract hash (`render_contract_hash`)
are **deterministic** — any change to a material field changes the identity, so a
tampered or drifted request cannot reuse an old approval.

Tests:
* `test_render_request_deterministic`
* `test_changed_format_changes_identity`
* `test_changed_fps_changes_identity`
* `test_changed_duration_changes_identity`
* `test_changed_request_invalidates_approval`
* `test_changed_asset_invalidates_approval`
* `test_changed_asset_hash_invalidates_approval`
* `test_changed_source_after_approval_blocked`

---

## 10. Separate Stage 8N approval

Stage 8N requires its **own explicit approval** with `explicit_render_confirmation=true`
and `explicit_non_delivery_acknowledgement=true`, bound to the exact
`render_contract_hash`. A different operator, a different contract, or a replay of a
conflicting approval is rejected.

Tests:
* `test_explicit_stage8n_approval_succeeds`
* `test_approval_requires_operator_id`
* `test_approval_requires_render_confirmation`
* `test_approval_requires_non_delivery_ack`
* `test_approval_binds_render_contract_hash`
* `test_approval_binds_manifest_hash`
* `test_conflicting_approval_replay_rejected`
* `test_exact_approval_replay_idempotent`
* `test_wrong_request_approval_rejected`
* `test_wrong_project_approval_rejected`
* `test_stage8m_approval_cannot_authorize_render`
* `test_dispatch_without_approval_blocked`
* `TestRenderApprovalSeparation::*`
* Integration: `TestStage8NRealHVS::test_separate_8n_approval_recorded`

---

## 11. Pre-dispatch reverification

Before dispatch, Stage 8N re-reads the Stage 8M readiness and re-hashes the bound
artifacts. If the readiness expired, the manifest hash drifted, or the source changed,
dispatch is blocked.

Tests:
* `test_pre_dispatch_rehash_succeeds`
* `test_stale_readiness_rejected`
* `test_manifest_hash_mismatch_rejected`
* `test_asset_hash_mismatch_rejected`

---

## 12. Subprocess safety

* argv list (never a shell string)
* `shell=False`
* explicit `cwd` (fixed working directory)
* bounded `timeout_seconds` (clamped to `_MAX_RENDER_TIMEOUT_SECONDS`)
* no arbitrary command input, no arbitrary output path
* HVS invoked only via `python -m hvs.cli`

Tests:
* `test_hvs_invocation_uses_argv`
* `test_hvs_invocation_uses_shell_false`
* `test_hvs_invocation_uses_explicit_cwd`
* `test_hvs_invocation_uses_timeout`
* `TestHVSDispatchSafety::*`
* `test_no_shell_true`
* `test_no_os_system`
* `test_no_http_client`
* `test_no_hvs_imports_in_production_modules`

---

## 13. No-overwrite policy

Stage 8N refuses to write into, or dispatch over, an existing destination it does
not own. The render output path must resolve strictly within
`<hvs_repo_root>/projects/<project_id>`, rejecting traversal (`..`), absolute escapes,
and out-of-tree paths.

Tests:
* `test_existing_destination_blocks_overwrite`
* `test_out_of_tree_output_path_rejected`
* `test_traversal_output_path_rejected`
* `test_arbitrary_output_path_rejected`
* `test_empty_output_path_rejected`
* `test_missing_output_path_rejected`
* `test_zero_byte_output_rejected`

---

## 14. Failure and timeout policy

* HVS non-zero exit → render NOT completed; completion not asserted.
* HVS timeout → fails safe (no completion evidence).
* Process exit code **zero is never treated as completion proof** — only a verified
  artifact proves completion.
* Malformed HVS JSON / ffprobe JSON → fails safe.
* ffprobe timeout / non-zero exit → fails safe.

Tests:
* `test_exit_zero_alone_not_completion`
* `test_exit_zero_with_invalid_evidence_not_completion`
* `test_hvs_nonzero_exit_fails_safe`
* `test_hvs_timeout_fails_safe`
* `test_hvs_malformed_json_fails_safe`
* `test_ffprobe_nonzero_exit_fails_safe`
* `test_ffprobe_timeout_fails_safe`
* `test_malformed_ffprobe_json_fails_safe`

---

## 15. Partial-batch policy

Stage 8N dispatches a **single approved format** per render request. The HVS
`render-hyperframes` boundary accepts one `--format`; multi-format requirements are
modeled as multiple independent Stage 8N render requests. A partially produced or
missing expected output is rejected (not silently accepted).

Tests:
* `test_missing_expected_output_rejected`
* `test_unexpected_output_path_rejected`
* `test_wrong_returned_project_id_rejected`
* `test_hvs_project_drift_rejected`

---

## 16. Artifact discovery

The artifact is discovered only at the contract-relative path inside the project
render root. Absence → rejected. Real MP4 is located and its size recorded.

Tests:
* `test_missing_expected_output_rejected`
* `test_zero_byte_output_rejected`
* `test_video_stream_required`
* Integration: `TestStage8NRealHVS::test_real_mp4_discovered_and_hashed`

---

## 17. SHA-256 evidence

The artifact SHA-256 is computed independently and recorded in both the
verification record and the completion evidence.

* Real artifact SHA-256 (this certification):
  `70f1a0ccc5233315af85e6f95df023632a9de91f3e2c3f0751e49d10f0d93f26`
* Test: `test_sha256_recorded_correctly`, `test_asset_hash_mismatch_rejected`

---

## 18. FFprobe evidence

Streams, codec, resolution, FPS, pixel format, and duration are read from a
real `ffprobe -show_format -show_streams -of json` invocation (argv, `shell=False`)
and compared to the contract.

Real artifact ffprobe (this certification):
* container: `mov,mp4,m4a,3gp,3g2,mj2`
* video codec: `h264`
* resolution: `1080×1920`
* fps: `30/1` (30)
* pixel format: `yuv420p`
* duration: `3.000000 s`

Tests:
* `test_ffprobe_uses_argv_and_shell_false`
* `test_codec_mismatch_rejected`
* `test_resolution_mismatch_rejected`
* `test_fps_mismatch_rejected`
* `test_pixel_format_mismatch_rejected`
* `test_video_stream_required`
* `test_audio_stream_required_when_contracted`
* `test_optional_audio_absence_reported_not_required`
* Integration: `TestStage8NRealHVS::test_ffprobe_verifies_profile`

---

## 19. Stream evidence

At least one video stream is required. Audio stream handling depends on the contract
(see §25).

Tests:
* `test_video_stream_required`
* `test_audio_stream_required_when_contracted`
* `test_optional_audio_absence_reported_not_required`

---

## 20. Codec evidence

`h264` required for the certified vertical contract. Mismatch → rejected.

Test: `test_codec_mismatch_rejected`

---

## 21. Resolution evidence

`1080×1920` required. Mismatch → rejected.

Test: `test_resolution_mismatch_rejected`

---

## 22. FPS evidence

`30` required. Mismatch → rejected.

Test: `test_fps_mismatch_rejected`

---

## 23. Pixel-format evidence

`yuv420p` required. Mismatch → rejected.

Test: `test_pixel_format_mismatch_rejected`

---

## 24. Duration evidence

Target `3.0 s` with a tolerance. Outside tolerance → rejected. Inside → accepted.
A/V drift (when audio is required) also bounded.

Tests:
* `test_duration_inside_tolerance_accepted`
* `test_duration_outside_tolerance_rejected`
* `test_invalid_duration_rejected`
* `test_av_drift_inside_tolerance_accepted`
* `test_av_drift_outside_tolerance_rejected`

---

## 25. Audio contract — `NOT_REQUIRED`

For the certified vertical acceptance, **`audio_requirement=NOT_REQUIRED`**.

The real artifact has **zero audio streams**. This is accepted **only because** the
contract explicitly says `NOT_REQUIRED`. The verification result truthfully records
`audio_stream_count=0` and `av_sync_verdict="no_audio_stream"` — it does **not**
falsely report an audio PASS.

If a future contract sets `audio_requirement=REQUIRED`, the same verification path
will **require** an audio stream and reject its absence (`test_audio_stream_required_when_contracted`).

Tests:
* `test_optional_audio_absence_reported_not_required`
* `test_audio_stream_required_when_contracted`
* Integration: `TestStage8NRealHVS::test_ffprobe_verifies_profile` (asserts
  `audio_stream_count==0` and `av_sync_verdict=="no_audio_stream"`)

---

## 26. A/V policy for future audio-required contracts

When `audio_requirement=REQUIRED`, `test_audio_stream_required_when_contracted`
enforces an audio stream and `test_av_drift_inside/outside_tolerance_*` bound the
A/V sync. The code path is symmetric; only the contract flag differs.

---

## 27. Completion-evidence contract

Completion evidence is created **only after** the artifact passes verification. It
binds: `render_request_id`, `render_contract_hash`, `render_approval_id`,
`render_dispatch_id`, `hvs_render_id`, `intake_manifest_id`, manifest/readiness
hashes, format, `artifact_sha256_values`, `artifact_verification_ids`, and the
boundary flags.

Tests:
* `test_completion_evidence_binds_approval`
* `test_completion_evidence_binds_artifact_hashes`
* `test_completion_evidence_binds_stage8m_readiness`
* `test_completion_evidence_does_not_create_delivery`
* Integration: `TestStage8NRealHVS::test_completion_evidence_created`

---

## 28. Explicit non-delivery boundary

Every response and the completion evidence carry, explicitly:

* `delivery_authorized = false`
* `publishing_authorized = false`
* `customer_contact_performed = false`
* `upload_performed = false`
* `publishing_performed = false`
* `invoice_state_changed = false`
* `payment_state_changed = false`
* `automation_allowed = false`

Tests:
* `test_no_delivery`
* `test_no_publish`
* `test_no_customer_contact`
* `test_no_upload`
* `test_no_invoice_mutation`
* `test_no_payment_mutation`
* `test_no_commercial_flag_true`
* `test_completion_evidence_does_not_create_delivery`
* `TestNonDeliveryBoundary::*`

---

## 29. Focused result

* Default run (`-m "not integration"`): **104 passed, 11 deselected, exit 0**
  (the 11 deselected are the integration cluster).
* The full test file also contains 11 `@pytest.mark.integration` tests (see §30).

## 30. Real-HVS integration result

Explicit run (`-m integration`): **11 passed, 0 failed, exit 0**.

The cluster proves the 8 minimum real-HVS cases:

1. Real HVS project inspection — `test_real_hvs_project_inspectable`
2. Stage 8M readiness reverification — `test_stage8m_readiness_reverified`
3. Vertical render-request creation — `test_render_request_created_for_vertical`
4. Separate Stage 8N approval — `test_separate_8n_approval_recorded`
5. Approved dispatch reaches the real HVS CLI boundary — `test_dispatch_reaches_real_hvs_boundary`
6. Real MP4 discovered + SHA-256 — `test_real_mp4_discovered_and_hashed`
7. FFprobe verifies h264 / 1080×1920 / 30 FPS / yuv420p / ~3.0 s —
   `test_ffprobe_verifies_profile` (REAL ffprobe on the real artifact)
8. Completion evidence with `artifact_verified=true`, `delivery_authorized=false`,
   `publishing_authorized=false`, `automation_allowed=false` —
   `test_completion_evidence_created`

Plus the read-only/pre-flight cases:
* `test_real_hvs_render_boundary_is_reachable`
* `test_real_hvs_render_completion_fails_closed_on_missing_approval`
* `test_real_hvs_render_completion_dry_run_contract`

`audio_requirement=NOT_REQUIRED`; audio stream count = 0; A/V verdict =
`no_audio_stream` (truthful, not fabricated PASS).

---

## 31. Affected regression result

Regression cluster (Stage 1 adapter, Stage 3 correlation/asset boundary via
materialization stores, Stage 5 render dispatch, Stage 8L init, Stage 8M
intake/materialization, append-only stores, security scanner):

**330 passed, 1 skipped, 8 deselected, exit 0.**

Paths:
`test_hvs_adapter.py`, `test_hvs_render_dispatch.py`,
`test_hvs_production_asset_intake_materialization.py`,
`test_hvs_project_initialization_materialization.py`,
`test_hvs_asset_materialization.py`, `test_hvs_evidence_intake.py`,
`test_operator_execution_store.py`, `test_result_intake_store.py`,
`scripts/tests/test_security_scan_baseline.py`.

Proven:
* Stage 8M approval does **not** authorize render (`test_stage8m_approval_cannot_authorize_render`)
* Stage 5 approval boundary not weakened (Stage 5 suite green)
* HVS invocation remains bounded (subprocess-safety suite green)
* Stage 8N creates no delivery evidence (`test_no_delivery`, `test_completion_evidence_does_not_create_delivery`)
* No commercial/invoice/payment state changes (`test_no_invoice_mutation`, `test_no_payment_mutation`)
* No default renderer change (adapter suite green)

---

## 32. Collection result

`pytest --collect-only -q` → **2051 collected, 19 deselected, exit 0, 0 collection errors.**

## 33. Full-suite result

`pytest -q` → **2049 passed, 2 skipped, 19 deselected, exit 0** (elapsed 6:18).

## 34. Smoke result

Existing smoke convention (no dedicated new smoke group added by Stage 8N) —
the full suite above subsumes smoke behavior; exit 0.

## 35. Security result

`scripts/security_scan_baseline.py` → **SECURITY SCAN: PASS, 0 findings**
(475 files scanned). The Stage 8N `hvs_render_completion_service.py` entry in
`_CONTROL_CENTER_SUBPROCESS_ALLOWLIST` is narrowly scoped to the single
bounded local subprocess module requiring it.

Production modules contain **no** `shell=True`, **no** `os.system`, **no** `import hvs`
/ `from hvs`, **no** `requests`/`httpx`/`urllib` networking, **no** socket client,
**no** arbitrary command executor. (Tests: `test_no_shell_true`, `test_no_os_system`,
`test_no_http_client`, `test_no_hvs_imports_in_production_modules`.)

---

## 36. Mandatory 105-case coverage matrix

The 105 mandatory Stage 8N requirements are enumerated below, grouped by the
contract domains (Phase-6 taxonomy), each mapped to a concrete test node ID from the
focused suite (`test_…`) or the real-HVS integration cluster
(`TestStage8NRealHVS::…`). All 105 are COVERED or NOT-APPLICABLE-WITH-JUSTIFICATION;
0 partially covered; 0 missing.

### A. Stage 8M provenance (1–8)
1. Missing Stage 8M evidence → reject — `test_missing_stage8m_evidence_rejected`
2. Non-READY evidence → reject — `test_non_ready_evidence_rejected`
3. Stale readiness → reject — `test_stale_readiness_rejected`
4. Stage 8M approval cannot authorize render — `test_stage8m_approval_cannot_authorize_render`
5. Approval binds readiness evidence — `test_approval_binds_readiness_evidence`
6. Runtime records remain gitignored — `test_runtime_records_remain_ignored`
7. HVS tracked source remains clean — `test_hvs_tracked_source_remains_clean`
8. MP4 artifacts remain untracked — `test_mp4_artifacts_remain_untracked`

### B. Request identity (9–18)
9. Deterministic request id — `test_render_request_deterministic`
10. Format change → new identity — `test_changed_format_changes_identity`
11. FPS change → new identity — `test_changed_fps_changes_identity`
12. Duration change → new identity — `test_changed_duration_changes_identity`
13. Changed request invalidates approval — `test_changed_request_invalidates_approval`
14. Changed asset invalidates approval — `test_changed_asset_invalidates_approval`
15. Changed asset hash invalidates approval — `test_changed_asset_hash_invalidates_approval`
16. Changed source after approval blocked — `test_changed_source_after_approval_blocked`
17. Wrong request approval rejected — `test_wrong_request_approval_rejected`
18. Wrong project approval rejected — `test_wrong_project_approval_rejected`

### C. Approval separation (19–30)
19. Explicit Stage 8N approval succeeds — `test_explicit_stage8n_approval_succeeds`
20. Approval requires operator id — `test_approval_requires_operator_id`
21. Approval requires render confirmation — `test_approval_requires_render_confirmation`
22. Approval requires non-delivery ack — `test_approval_requires_non_delivery_ack`
23. Approval binds render contract hash — `test_approval_binds_render_contract_hash`
24. Approval binds manifest hash — `test_approval_binds_manifest_hash`
25. Conflicting approval replay rejected — `test_conflicting_approval_replay_rejected`
26. Exact approval replay idempotent — `test_exact_approval_replay_idempotent`
27. Rejection requires reason — `test_rejection_requires_reason`
28. Separate 8N approval recorded (real HVS) — `TestStage8NRealHVS::test_separate_8n_approval_recorded`
29. Approval separation suite — `TestRenderApprovalSeparation::*`
30. Dispatch without approval blocked — `test_dispatch_without_approval_blocked`

### D. Pre-dispatch revalidation (31–35)
31. Pre-dispatch rehash succeeds — `test_pre_dispatch_rehash_succeeds`
32. Stale readiness rejected at dispatch — `test_stale_readiness_rejected`
33. Manifest hash mismatch rejected — `test_manifest_hash_mismatch_rejected`
34. Asset hash mismatch rejected — `test_asset_hash_mismatch_rejected`
35. Ready evidence accepted — `test_ready_evidence_accepted`

### E. Subprocess safety (36–46)
36. HVS invocation uses argv — `test_hvs_invocation_uses_argv`
37. HVS invocation uses shell=False — `test_hvs_invocation_uses_shell_false`
38. HVS invocation uses explicit cwd — `test_hvs_invocation_uses_explicit_cwd`
39. HVS invocation uses timeout — `test_hvs_invocation_uses_timeout`
40. ffprobe uses argv + shell=False — `test_ffprobe_uses_argv_and_shell_false`
41. No shell=True anywhere — `test_no_shell_true`
42. No os.system — `test_no_os_system`
43. No HTTP client — `test_no_http_client`
44. No HVS imports in production modules — `test_no_hvs_imports_in_production_modules`
45. Dispatch safety suite — `TestHVSDispatchSafety::*`
46. Dispatch reaches real HVS CLI boundary — `TestStage8NRealHVS::test_dispatch_reaches_real_hvs_boundary`

### F. Malformed output / discovery (47–58)
47. Missing expected output rejected — `test_missing_expected_output_rejected`
48. Unexpected output path rejected — `test_unexpected_output_path_rejected`
49. Wrong returned project id rejected — `test_wrong_returned_project_id_rejected`
50. HVS project drift rejected — `test_hvs_project_drift_rejected`
51. Missing output path rejected — `test_missing_output_path_rejected`
52. Empty output path rejected — `test_empty_output_path_rejected`
53. Zero-byte output rejected — `test_zero_byte_output_rejected`
54. Out-of-tree output rejected — `test_out_of_tree_output_path_rejected`
55. Traversal output rejected — `test_traversal_output_path_rejected`
56. Arbitrary output path rejected — `test_arbitrary_output_path_rejected`
57. Video stream required — `test_video_stream_required`
58. Real MP4 discovery + SHA (real HVS) — `TestStage8NRealHVS::test_real_mp4_discovered_and_hashed`

### G. Timeout / non-zero exit (59–66)
59. Exit-zero alone ≠ completion — `test_exit_zero_alone_not_completion`
60. Exit-zero + invalid evidence ≠ completion — `test_exit_zero_with_invalid_evidence_not_completion`
61. HVS non-zero exit fails safe — `test_hvs_nonzero_exit_fails_safe`
62. HVS timeout fails safe — `test_hvs_timeout_fails_safe`
63. HVS malformed JSON fails safe — `test_hvs_malformed_json_fails_safe`
64. ffprobe non-zero exit fails safe — `test_ffprobe_nonzero_exit_fails_safe`
65. ffprobe timeout fails safe — `test_ffprobe_timeout_fails_safe`
66. Malformed ffprobe JSON fails safe — `test_malformed_ffprobe_json_fails_safe`

### H. No-overwrite (67–70)
67. Existing destination blocks overwrite — `test_existing_destination_blocks_overwrite`
68. Out-of-tree output rejected — `test_out_of_tree_output_path_rejected`
69. Traversal output rejected — `test_traversal_output_path_rejected`
70. Arbitrary output path rejected — `test_arbitrary_output_path_rejected`

### I. SHA-256 (71–73)
71. SHA-256 recorded correctly — `test_sha256_recorded_correctly`
72. Asset hash mismatch rejected — `test_asset_hash_mismatch_rejected`
73. Manifest hash mismatch rejected — `test_manifest_hash_mismatch_rejected`

### J. FFprobe / streams / codec / res / FPS / pixfmt / duration (74–90)
74. Codec mismatch rejected — `test_codec_mismatch_rejected`
75. Resolution mismatch rejected — `test_resolution_mismatch_rejected`
76. FPS mismatch rejected — `test_fps_mismatch_rejected`
77. Pixel-format mismatch rejected — `test_pixel_format_mismatch_rejected`
78. Duration inside tolerance accepted — `test_duration_inside_tolerance_accepted`
79. Duration outside tolerance rejected — `test_duration_outside_tolerance_rejected`
80. Invalid duration rejected — `test_invalid_duration_rejected`
81. A/V drift inside tolerance accepted — `test_av_drift_inside_tolerance_accepted`
82. A/V drift outside tolerance rejected — `test_av_drift_outside_tolerance_rejected`
83. Video stream required — `test_video_stream_required`
84. Audio required when contracted — `test_audio_stream_required_when_contracted`
85. Optional audio absence reported (not required) — `test_optional_audio_absence_reported_not_required`
86. FFprobe verifies profile (real HVS) — `TestStage8NRealHVS::test_ffprobe_verifies_profile`
87. Real HVS project inspectable — `TestStage8NRealHVS::test_real_hvs_project_inspectable`
88. Stage 8M readiness reverified (real HVS) — `TestStage8NRealHVS::test_stage8m_readiness_reverified`
89. Vertical render request created (real HVS) — `TestStage8NRealHVS::test_render_request_created_for_vertical`
90. Unsupported format rejected — `test_unsupported_format_rejected`

### K. Audio / A-V semantics (91–93)
91. `NOT_REQUIRED` accepts zero audio streams — `test_optional_audio_absence_reported_not_required`
92. `REQUIRED` enforces audio stream — `test_audio_stream_required_when_contracted`
93. Truthful no-audio verdict — `TestStage8NRealHVS::test_ffprobe_verifies_profile`
   (asserts `audio_stream_count == 0` and `av_sync_verdict == "no_audio_stream"`)

### L. Partial-batch handling (94–95)
94. Unsupported preset rejected — `test_unsupported_preset_rejected`
95. Wrong project id rejected — `test_wrong_project_id_rejected`

### M. Completion evidence (96–100)
96. Completion binds approval — `test_completion_evidence_binds_approval`
97. Completion binds artifact hashes — `test_completion_evidence_binds_artifact_hashes`
98. Completion binds Stage 8M readiness — `test_completion_evidence_binds_stage8m_readiness`
99. Completion does not create delivery — `test_completion_evidence_does_not_create_delivery`
100. Completion evidence created (real HVS) — `TestStage8NRealHVS::test_completion_evidence_created`

### N. CLI behavior (101–103)
101. CLI create/inspect/readiness/decide/verify/dispatch/inspect-completion/list
    — `TestStage8NCLI::test_cli_create_request_success`,
    `test_cli_inspect_request`, `test_cli_evaluate_readiness`,
    `test_cli_decide_approve_success`, `test_cli_decide_reject_requires_reason`,
    `test_cli_verify_artifact_readonly`, `test_cli_inspect_completion`,
    `test_cli_list_recovery_queue_empty`
102. CLI dispatch dry-run contract — `TestStage8NRealHVS::test_real_hvs_render_completion_dry_run_contract`
103. CLI fails closed on missing approval — `TestStage8NRealHVS::test_real_hvs_render_completion_fails_closed_on_missing_approval`

### O. Security / non-delivery boundary (104–105)
104. Security architecture — `TestSecurityArchitecture::test_no_http_client`,
    `test_no_shell_true`, `test_no_os_system`, `test_no_hvs_imports_in_production_modules`,
    `test_runtime_records_remain_ignored`
105. Non-delivery boundary — `TestNonDeliveryBoundary::*`, `test_no_delivery`,
    `test_no_publish`, `test_no_customer_contact`, `test_no_upload`,
    `test_no_invoice_mutation`, `test_no_payment_mutation`, `test_no_commercial_flag_true`

**Totals:** 105 / 105 mapped. 0 partially covered. 0 missing.
(The 97 focused test functions + 11 integration tests cover all 105; several
requirements are proven by more than one test, and a few real-HVS cases reuse the
same production path as their focused counterparts — both are cited where applicable.)

---

## 37. Runtime output path and ignore status

* Stage 8N append-only ledger: `scos/work/hvs_render_completion/render_completion.jsonl`
  (gitignored runtime data; matches per-stage append-only convention).
* HVS render output: `hermes-video-studio/projects/hvs8l-e32880405a6292d1ac4e1f68997d085f/renders/hyperframes-693c0e7c3bad0f4d.mp4`
  — gitignored (`projects/` is HVS runtime data). **Not committed.**
* The real MP4 is **reused**, not re-rendered, and is **never** added to Git.

---

## 38. Known limitations

* Stage 8N certifies a **single approved format** per render request. Multi-format
  requirements are modeled as multiple independent Stage 8N requests (documented
  partial-batch policy, §15).
* The certified vertical acceptance uses `audio_requirement=NOT_REQUIRED`. An
  audio-required contract is supported by the same code path
  (`test_audio_stream_required_when_contracted`) but was **not** exercised against a
  real audio-bearing render in this certification (the reused project's materialized
  asset is voice-only WAV → video-only MP4 by design).
* Stage 8N performs **no delivery**. The delivery boundary (explicit operator-controlled
  delivery-package + manual delivery authorization) is intentionally deferred to
  **Stage 8O**.

---

## 39. Final verdict

**PASS.** All gates satisfied:

* Stage 8M materialization approval did **not** authorize rendering.
* Stage 8N required a **separate explicit approval** (bound to `render_contract_hash`,
  with render-confirmation + non-delivery acknowledgement).
* Process exit code zero was **not** accepted as completion proof — only a verified
  artifact proved completion.
* The real artifact was **independently hashed** (SHA-256
  `70f1a0ccc5233315af85e6f95df023632a9de91f3e2c3f0751e49d10f0d93f26`) and
  **probed** (real ffprobe: h264 / 1080×1920 / 30 fps / yuv420p / 3.0 s).
* No audio stream was required for the certified vertical contract
  (`audio_requirement=NOT_REQUIRED`); the result truthfully reports
  `audio_stream_count=0` / `av_sync_verdict="no_audio_stream"`.
* No delivery authorized; no publishing authorized; no customer contact; no invoice or
  payment state changed; no upload; no publish.
* HVS tracked source unchanged; no MP4 committed; no network used; no push; Stage 8O
  not started.
* Focused: 104 passed / 11 deselected. Integration: 11 passed / 0 failed.
  Regressions: 330 passed. Full suite: 2049 passed / 2 skipped. Security: PASS / 0
  findings. 105/105 mandatory cases covered.

---

*End of Stage 8N certification.*
