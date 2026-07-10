# SCOS–HVS Integration — Stage 4 Certification

**Title:** SCOS–HVS Integration Stage 4 — Asset Reference Resolution and
Approval-Gated Local Asset Materialization

**Verdict:** PASS

**Date of certification:** 2026-07-10

---

## 1. Objective and Explicit Non-Goals

### Objective
Implement a narrow, deterministic bridge that:
1. Resolves each Stage 2 HVS asset reference to an approved local source asset.
2. Validates the source asset against an explicit safe local asset policy.
3. Requires a separate valid approval (`materialize_hvs_assets`) before copying.
4. Materializes approved assets into the correlated HVS project safely (copy-only).
5. Creates a deterministic HVS-side asset manifest and SCOS correlation evidence.
6. Is idempotent (retries do not duplicate copies).
7. Supports dry-run with zero filesystem mutation.
8. Does **not** render or otherwise process media.

### Non-Goals (hard exclusions enforced)
- No network access, cloud API, browser automation, credentials, push/pull/fetch.
- No package installation or dependency changes.
- No rendering, FFmpeg, media assembly, voice generation, AI generation, asset
  download, publishing, delivery, quality analysis, memory workflow, or
  default-renderer change.
- No modification of Stage 1–3 mapping, approval, creation, correlation, or
  idempotency semantics.
- No materialization of any source asset without a valid explicit approval.
- No deletion, overwrite, move, rename, or modification of the source asset.
- No acceptance of arbitrary paths, symlink escapes, path traversal, device
  paths, or URLs.
- No Stage 5 (render dispatch) work — not begun.

---

## 2. Exact SCOS / HVS Baselines

| Repo | Branch | HEAD | Working tree |
|------|--------|------|--------------|
| SCOS | `main` | `811517050a2f7f9a3ddfccb92be7f06840a47ef3` (Stage 3 commit) | clean at start; 2 new untracked files at cert time |
| HVS  | `main` | `8c0708d71f92ed5a417ce6ee678ae28f76c39944` | clean, unchanged |

Both baselines match the required starting state exactly. HVS was **not** mutated
by any test or operation (verified by `git status` — empty — at the end of all runs).

---

## 3. Discovered Interfaces (read-only, consumed not duplicated)

### SCOS (Stage 2 / Stage 3)
- `hvs_contract_models.SCOSAssetRef(asset_id, asset_type, path)` — logical asset
  reference (logical id, never a path).
- `hvs_schema_mapper.map_scos_to_hvs`, `validate_hvs_payload`,
  `payload_identity_hash`, `canonicalize_mapping_payload`, `_sha256_hex16`,
  `_reject_path_traversal`, `X_SCOS_KEY`.
- `hvs_project_creation.CorrelationLedger` / `CorrelationRecord` /
  `correlation_id_for` / `CONTRACT_VERSION` / `UnsafeTargetError` /
  `HVSProjectApproval` patterns / slug-safety discipline
  (`projects/<pid>` must not escape root).
- Stage 4 **reads** the Stage 3 correlation ledger to (a) prove the target HVS
  project is a Stage-3-correlated project and (b) recover its `hvs_project_id`
  and `hvs_artifact_id`. `create_hvs_project()` is **not modified** — no seam
  was needed because Stage 4 consumes the existing public ledger API.

### HVS (observed layout, read-only)
- Project layout: `projects/<pid>/assets/asset_manifest.json`,
  `asset_slots/<sid>.json`.
- `asset_slots/<sid>.json` carries `slot_type` + `accepted_formats`.
- **Key observation:** Stage 2's emitted `asset_slots` carry **empty**
  `accepted_formats`. Therefore the effective extension allow-list is the
  canonical HVS slot-type map derived from the real HVS
  `project/asset_slots/s01.json` sample (background, subject, overlay_text,
  music_or_audio_placeholder, optional_b_roll). Documented in §5.
- Stage 4 writes a **distinct** SCOS-authored manifest at
  `assets/asset_manifest.stage4.json` to avoid any collision with the native
  HVS `assets/asset_manifest.json`.

---

## 4. Source-Root Policy

- Source roots are **injected explicitly** as `SourceRoot(root_id, root_path)`;
  only the `root_id` is persisted, never the absolute path.
- Resolution requires `resolved_path.relative_to(Path(root_path).resolve())`.
- Rejected: null bytes, UNC/network paths (`\\`/`//` not drive-mapped), URLs
  (`://`), device paths (`\\.\`), absolute caller paths, `..` traversal,
  symlink escapes, non-regular files, non-positive sizes.
- No discovery of files outside explicitly approved roots (the relative path is
  taken from the Stage 2 `asset.path`; wildcard discovery is forbidden).
- `resolve_source_root` validates the configured root eagerly (rejects unsafe
  roots before any per-asset resolution).

---

## 5. Asset Resolution Rules

Each resolved asset (`ResolvedAsset`) contains exactly:
- `source_asset_id`
- `source_relative_path` (relative to approved root; stored, not absolute)
- `source_root_id`
- `source_file_sha256` (full SHA-256, streamed, deterministic)
- `source_size_bytes`
- `source_extension`
- `declared_slot_id` (== SCOS asset id)
- `declared_slot_type`
- `materialization_identity_hash` (`_sha256_hex16` over correlation_id, asset_id,
  root_id, relative path, sha, size, slot_type, intended destination)
- `intended_hvs_relative_path` (`assets/<slot_type>/<sha[:16]>-<safe_basename>`)
- `resolution_status` (`resolved`)

**Slot-type → accepted extension allow-list (canonical, never extended):**
- `background` → `.png .jpg .jpeg .mp4`
- `subject` → `.png .jpg .jpeg .webp`
- `overlay_text` → `.srt .ass .txt`
- `music_or_audio_placeholder` → `.mp3 .wav .m4a`
- `optional_b_roll` → `.mp4 .mov`

Validation order: asset-reference well-formed → declared path traversal check →
slot-type in allow-list → resolved under approved root → not a symlink → exists
& regular file → positive size → extension in allow-list → SHA-256 streamed →
optional pinned-SHA match (hard fail on change). No fallback, no silent clamp.

---

## 6. Approval State / Consumption Rules

New narrow model `HVSAssetMaterializationApproval` with
`action_type = "materialize_hvs_assets"` (distinct from Stage 3
`create_hvs_project`). Scope fields:
`approval_id`, `action_type`, `status`, `requested_correlation_id`,
`requested_scos_project_id`, `requested_hvs_artifact_id`,
`requested_asset_manifest_identity_hash`, `approved_source_root_ids`,
`approved_asset_ids`, `issued_by`, optional `issued_at`/`expires_at`/`reason`.

Materialization proceeds only when **all** hold:
1. status exactly `approved`; 2. action type matches; 3. correlation /
   SCOS project / HVS artifact all match; 4. resolved asset manifest identity
   matches approval scope; 5. every source root approved; 6. every source asset
   approved; 7. correlated HVS project exists & is valid; 8. all resolved assets
   pass validation; 9. no destination conflict.

**Consumption:** a persisted `MaterializationRecord` (append-only SCOS ledger)
keyed to the approval_id is the consumption record. It is written **only after**
all copies + HVS manifest persist successfully. Pre-copy failures (including
destination conflict) leave the approval reusable; it is never consumed.

**Denial taxonomy (zero mutation):** `approval_required`, `approval_not_valid`,
`approval_action_mismatch`, `approval_scope_mismatch`, `correlation_not_found`,
`invalid_asset_reference`, `unsafe_source_path`, `unsupported_asset_type`,
`source_asset_missing`, `source_asset_changed`, `destination_conflict`,
`unsafe_target`, `materialization_not_supported`.

---

## 7. Destination Layout

`projects/<hvs_pid>/assets/<slot_type>/<source_sha256[:16]>-<safe_basename>`

- Deterministic, project-local, always beneath the Stage 3 correlated HVS
  project root.
- `safe_basename` collapses `..`, strips separators, replaces any char outside
  `[A-Za-z0-9._-]` with `_`, capped to 128 chars, never empty.
- Source bytes preserved exactly (`shutil.copyfile`); destination verified by
  re-hashing after copy.
- Destination outside the project assets dir is impossible: both the resolver
  and the executor perform `relative_to(assets_dir)` containment checks.

---

## 8. Manifest and Evidence Schemas

### HVS-side asset manifest (`assets/asset_manifest.stage4.json`)
```
schema_version: "scos-hvs.asset-materialization.v1/1.0.0"
contract_version
semantic_version
correlation_id
hvs_project_id
hvs_artifact_id
asset_manifest_identity_hash
approved_source_root_ids: [root_id, ...]   # ids only, no absolute paths
asset_count
assets: [ { source_asset_id, slot_id, slot_type, source_root_id,
           source_relative_path, source_sha256, source_size_bytes,
           source_extension, materialization_identity_hash,
           destination_relative_path, status: materialized|reused } ]
created_at: null   # Stage 2 deterministic placeholder; no clock invented
```

### SCOS-side materialization evidence (`MaterializationRecord`, append-only JSONL)
```
schema_version: 1
materialization_id: "mat-<manifest_identity_hash>"
correlation_id
contract_version
scos_project_id
hvs_artifact_id
hvs_project_id
approval_id
manifest_identity_hash
materialization_status: created|reused
asset_fingerprints: [ {asset_id, sha256, destination_relative_path}, ... ]
```
No absolute source path, no secret data. Relative destination paths only.

---

## 9. Idempotency and Recovery Rules

- Same approved semantic asset set → exactly one copy; retry returns `reused`
  evidence and writes no new files.
- Existing **byte-identical** destination → `reused` (no copy).
- Existing **mismatched** destination (different SHA-256) → `destination_conflict`,
  operation aborts **before any write**; the original is never overwritten.
- Changed source file at the same path (vs. pinned/observed SHA) → `source_asset_changed`.
- Partially-interrupted state (some destinations present, no evidence record):
  re-run recomputes per-asset status; byte-identical files are reused, missing
  ones are copied → no duplicates.
- **Divergent asset set** for an active correlation (different manifest identity
  already materialized) → `destination_conflict` (documented rule: one active
  correlation owns exactly one asset set; re-materialization of a different set
  is not supported without a new correlation).

---

## 10. Error Taxonomy
See §6 (denial taxonomy). Each is a structured `error_kind` with `error_detail`
surfaced via `HVSAssetMaterializationOutcome` (`to_adapter_error()` /
`to_adapter_result()`), with **zero** filesystem mutation on denial.

---

## 11. Test Matrix (commands + results)

All tests use temporary fixture directories only; the real HVS repository is
never touched.

| # | Area | Test | Result |
|---|------|------|--------|
| 1 | Preflight | stage2 asset refs consumed | PASS |
| 2 | Preflight | stage3 correlation required | PASS |
| 3 | Dry-run | zero mutation (no HVS/manifest/ledger) | PASS |
| 4 | Preflight | canonical identity stable + reorder-invariant | PASS |
| 5 | Safety | missing source fails | PASS |
| 6 | Safety | path traversal fails | PASS |
| 7 | Safety | absolute/UNC/URL/symlink/null-byte rejected | PASS |
| 8 | Safety | unsupported type / slot mismatch fails | PASS |
| 9 | Safety | source outside approved root fails | PASS |
| 10 | Safety | source changed after planning fails | PASS |
| 11 | Safety | destination cannot escape / basename sanitized | PASS |
| 12 | Safety | source file never modified | PASS |
| 13 | Approval | missing/pending/rejected/expired/cancelled → zero mutation | PASS |
| 14 | Approval | wrong action type rejected | PASS |
| 15 | Approval | correlation/project/artifact mismatch rejected | PASS |
| 16 | Approval | asset-manifest identity mismatch rejected | PASS |
| 17 | Approval | unapproved root / asset rejected | PASS |
| 18 | Approval | approval reusable after pre-copy conflict | PASS |
| 19 | Approval | approval consumed only after all copies + evidence persist | PASS |
| 20 | Materialize | exact bytes copied into project-local destination | PASS |
| 21 | Materialize | HVS manifest valid + deterministic | PASS |
| 22 | Materialize | SCOS evidence append-only, no absolute path / secret | PASS |
| 23 | Materialize | no render/media/network/subprocess side effects | PASS |
| 24 | Materialize | destination conflict never overwrites | PASS |
| 25 | Idempotency | same request twice → one copy + reused | PASS |
| 26 | Recovery | existing matching destination recovered as reused | PASS |
| 27 | Recovery | partial interrupted state recovered, no duplicates | PASS |
| 28 | Recovery | divergent asset set follows conflict rule | PASS |
| 29 | Safety | inputs + approval objects not mutated | PASS |
| 30 | Regression | stage1/2/3 import surface intact | PASS |
| 31 | Cross-repo | produced manifest at expected path; HVS schema present (read-only) | PASS |
| 32 | Security | no forbidden network/AI/render/subprocess/unsafe patterns | PASS |

**Focused Stage 4 suite:** `32 passed` (command:
`pytest scos/control_center/tests/test_hvs_asset_materialization.py`).

### Regression / suites
- Stage 1+2+3 focused: `108 passed` (project creation + schema mapper + adapter).
- Control Center suite (`scos/control_center/tests/`): `773 passed`, 1 pre-existing
  unrelated warning (subprocess decode in `test_hvs_adapter`).
- Full SCOS suite (`scos/ integrations/`, **excluding 11 pre-existing
  numpy-import modules** — see §12): `1138 passed`, 2 warnings, 305s.

---

## 12. Environment Exception (documented, not a silent PASS)

The full-suite collection **would** block on 11 pre-existing test modules that
`import numpy` and fail at collection (`ModuleNotFoundError: No module named
'numpy'`). This is a verified pre-existing environment dependency gap — **none**
of these modules import or exercise Stage 4 code. Per the mandated gate, no
dependency was installed. The exact failing modules (collected verbatim):

```
scos/analytics/tests/test_feedback_engine.py
scos/assets/tests/test_asset_builder.py
scos/assets/tests/test_asset_builder_v2.py
scos/pipeline/tests/test_learning_pipeline.py
scos/qualification/tests/test_system_qualification.py
scos/replay/tests/test_analytics_replay.py
integrations/highlight/tests/test_highlight_engine.py
integrations/highlight/tests/test_narrative_engine.py
integrations/shortgen/tests/test_montage.py
integrations/shortgen/tests/test_short_generator.py
integrations/shortgen/tests/test_smoke_pipeline.py
```

All 11 fail at **import/collection** (`import numpy as np`), unrelated to Stage 4.
They were excluded and every collectable suite ran green (1138 passed). Installing
`numpy` would let the full suite run un-excluded, but that is a dependency change
outside this stage's scope and was intentionally left untouched.

---

## 13. Security Scan

- Static scan of `hvs_asset_materialization.py` against forbidden patterns
  (network libs, AI libs, `ffmpeg`/`moviepy`, `subprocess`, `shell=True`,
  `__import__`, `render`/`transcode`/`ffmpeg`/`moviepy` *usage*) → **no hits**
  (test 32).
- Copy-only primitive is `shutil.copyfile` (byte-exact). No `subprocess`,
  `os.system`, `shell=True`, `__import__`, network, AI, render, transcode, or
  HVS import anywhere in the module.
- No secrets persisted; evidence stores only root ids + relative paths.
- Path traversal, symlink escape, UNC/URL/device paths, and null bytes rejected
  at resolution (tests 6, 7).
- The only occurrences of the word "render"/"transcode" in the file are inside
  the negative-safety docstrings ("No rendering…", "no transform/render/network"),
  which the structural scan correctly ignores.

---

## 14. Real HVS Non-Mutation Proof

```
$ cd C:\Workspace\hermes-video-studio && git status --short
   (empty)
$ git rev-parse HEAD
   8c0708d71f92ed5a417ce6ee678ae28f76c39944
```
HVS working tree is clean and HEAD is unchanged after all Stage 4 tests and the
full SCOS suite run. No Stage 4 test writes under the real HVS repository (all
use injected temp `hvs_root`).

---

## 15. Changed Files

| File | Status | Purpose |
|------|--------|---------|
| `scos/control_center/hvs_asset_materialization.py` | added | Stage 4 implementation (models, resolution, approval gate, materialization executor, manifest, evidence, public API `materialize_hvs_assets`) |
| `scos/control_center/tests/test_hvs_asset_materialization.py` | added | 32 focused deterministic tests |
| `docs/certification/SCOS-HVS-integration-stage-4-asset-materialization.md` | added | this certification |

No modification to Stage 1–3 files. `create_hvs_project()` unchanged.

---

## 16. Limitations

- The effective slot-type → extension allow-list is the canonical HVS map; Stage
  2's emitted `accepted_formats` are empty, so the canonical map is authoritative.
- `created_at` in the HVS manifest is the Stage 2 deterministic placeholder
  (`null`) — no wall-clock invented at any stage.
- Approval `expires_at` is only evaluated when an injectable `clock` is supplied.
- Full-suite collection excludes 11 pre-existing numpy-dependent modules (§12).

---

## 17. Rollback

Stage 4 is additive (3 new files, no edits to existing modules). Rollback is a
single `git revert` / `git rm` of the three added files; no migration, no state
in the real HVS repo, and the Stage 3 correlation ledger is unaffected.

---

## 18. Final Verdict

**PASS.** All in-scope gates are green: 32 focused Stage 4 tests pass; Stage 1–3
regression (108) passes; Control Center suite (773) passes; full collectable SCOS
suite (1138) passes; HVS repo verified clean; security scan clean; dry-run and
safety/denial taxonomies proven; idempotency and recovery proven.

**Recommendation (separate approval required — NOT begun):** Stage 5 —
"Approval-Gated HVS Render Dispatch and Render Evidence Intake".
