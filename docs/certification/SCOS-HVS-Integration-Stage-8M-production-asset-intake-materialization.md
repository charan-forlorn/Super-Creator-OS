# SCOS-HVS Integration Stage 8M Production Asset Intake Materialization

## 1. Stage Objective

Stage 8M consumes a certified Stage 8L verified HVS project, derives the
approval-gated production-asset intake requirements, registers operator-owned
source assets under a locked intake root, records rights evidence, evaluates
bindings, builds an immutable intake manifest, gates readiness, requires explicit
operator approval (with explicit materialization confirmation and an explicit
non-render acknowledgement), materializes the approved assets into the verified
HVS runtime via the EXISTING `import-media` boundary, post-verifies the
materialized assets, and evaluates HVS render-readiness.

Stage 8M does not authorize rendering, publishing, uploading, customer contact,
asset generation, external distribution, invoicing, payment-provider access, or
any HVS mutation other than `import-media` (and the read-only `inspect-project` /
`media-readiness` probes). Stage 8M produces NO render and NO MP4.

## 2. Baselines

- Starting SCOS baseline: `37ce76f`
- Actual compatible SCOS baseline before edits: `37ce76f`
- SCOS branch: `main`
- HVS Stage 8L verified project reused: `2d55b371656c45c18e24a997a69025abd21b675e`
- HVS verified project id: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- HVS branch: `main`
- HVS source policy: read-only; no HVS commit authorized.

## 3. Architecture Blocker Resolved By Stage 8M

The Stage 1 adapter (`HermesVideoStudioAdapter`) forbids `import-media` and only
parses JSON. Stage 8M drives `import-media` through a dedicated, bounded
subprocess runner that mirrors the Stage 1 adapter discipline
(`subprocess.run(list, shell=False, fixed executable, fixed cwd, bounded
timeout, bounded stdout/stderr, no caller-controlled fragments`). This is the
same safe pattern already allowlisted for `hvs_adapter.py` and
`hvs_render_dispatch.py`.

The HVS `gate_codec` requires a duration-bearing stream for every role, so
images and MP4-less visuals are BLOCKED by HVS itself. Stage 8M therefore
requires exactly one satisfiable required asset — a synthetic operator-owned
voice asset (project-level, no scene-id) materialized from a WAV file with a
duration probe. Per-scene visual and music roles are OPTIONAL and are NOT
hardened into the mandatory readiness gate because hardening them would require
generating MP4/render, which Stage 8M is explicitly forbidden from doing.

## 4. Architecture Reused

- Stage 1 adapter reused for the HVS boundary contract (forbidden `import-media`
  guard preserved; Stage 8M does NOT use the adapter — it uses its own runner).
- Stage 4 safe-path helpers reused: `_assert_not_network_or_device`,
  `_safe_basename`, `_sha256_stream`.
- Stage 8L reverification reused as the entry point (certified project + live
  `inspect-project`).
- HVS `import-media` used (existing boundary only).
- HVS `inspect-project` and `media-readiness` used (read-only probes).
- HVS `media/media_manifest.json` read read-only for post-materialization
  verification (no HVS import into SCOS).
- SCOS-local ffprobe probe implemented (`_probe_media_local`) — HVS `media_probe`
  is NOT imported, preserving the architecture boundary.
- Backward-compatible extensions: bounded HVS CLI runner, append-only Stage 8M
  intake store, Stage 8M models/service/CLI.
- Duplicate mapper added: NO
- Stage 3 direct filesystem creator used: NO
- HVS legacy `create-project` used: NO

## 5. Contracts

Stage 8M adds:

- `ProductionAssetRequirement`: per required/optional role + scene requirement
  with allowed media types, rights requirement, and satisfaction status.
- `SourceAssetDescriptor`: operator-owned source registered under the locked
  intake root, with sha256, media type, and safe basename.
- `SourceAssetValidation`: probe status, media type, path-safety, extension
  consistency.
- `AssetRightsEvidence`: operator-owned / licensed / public-domain confirmation
  with blocking-class detection.
- `ProductionAssetBinding`: requirement→source compatibility verdict.
- `ProductionAssetIntakeManifest`: immutable intake contract
  (schema `scos-hvs.asset-intake-manifest.v1/1.0.0`) binding source hashes,
  rights hashes, requirement-set hash, and manifest content hash.
- `AssetMaterializationApproval`: operator approval bound to the manifest
  content hash, source sha256 values, and rights evidence hashes.
- `AssetMaterializationResult` / `PostMaterializationVerification` /
  `HVSRenderReadinessResult`: execution, verification, and readiness evidence.

## 6. Eligibility Contract

Stage 8M re-verifies before mutation:

- Stage 8L HVS project exists, is verified, and has not started rendering.
- HVS reports `render_started=false`, `voice_generated=false`,
  `placeholder_assets_generated=false`.
- Derived requirements: exactly one REQUIRED voice asset (project-level),
  optional per-scene visual + music.
- Intake readiness requires: valid source assets, compatible bindings, valid
  (non-blocking) rights evidence for every source asset, and no conflicts.
- Materialization requires explicit operator approval with
  `explicit_materialization_confirmation=True` AND
  `explicit_non_render_acknowledgement=True`.

## 7. Deterministic Intake And Source Root

- Locked intake root: `<repo_root>/scos/work/hvs_asset_intake` (gitignored).
- `register_source_asset` rejects any source outside this root
  (`SOURCE_OUTSIDE_ROOT`) unless an explicit `allowed_root` is supplied.
- Path traversal, UNC, URL, symlink, null-byte, newline, device, and executable
  content are rejected.
- Source sha256 is computed at registration and re-verified immediately before
  execution (`pre_execution_reverify`) so a changed or missing source blocks
  materialization.
- Manifest id and content hash are deterministic from their inputs; identical
  inputs replay to the same id (idempotent).

## 8. Operator Gate And Subprocess Boundary

Materialization requires:

- explicit operator ID
- explicit recorded date
- explicit materialization confirmation
- explicit non-render acknowledgement
- HVS repo root with `hvs/cli`
- HVS repository-local Python executable

Subprocess runner guarantees:

- argv list (no shell interpolation)
- `shell=False`
- explicit `cwd` (inherited, non-empty environment — empty env causes
  intermittent Windows failures)
- bounded timeout
- bounded stdout/stderr excerpts (4000 chars)
- absolute resolved source path passed to HVS (HVS runs in its own cwd)
- no HVS Python package import
- only `import-media` (mutation) plus read-only `inspect-project` /
  `media-readiness`

## 9. HVS Result Validation And Verification

SCOS does not trust exit code alone. Materialization verification requires:

- `import-media` VERDICT: PASS
- requested project id equals the manifest project id
- the materialized asset is found in HVS `media/media_manifest.json`
- the destination sha256 matches the approved source sha256 (no transform)
- post-materialization `inspect-project` confirms project semantic integrity
  (project id matches, `render_started=false`)
- no MP4 / render output detected in the HVS project directory

## 10. Replay, Conflict, And No-Overwrite

- Exact replay of an approved manifest yields identical manifest id and content
  hash (idempotent).
- A tampered manifest (changed content hash or requirement-set hash) is rejected
  before any HVS mutation (`MANIFEST_CHANGED_AFTER_APPROVAL`,
  `REQUIREMENT_SET_CHANGED`).
- A changed or missing approved source is rejected before mutation
  (`SOURCE_ASSET_CHANGED_AFTER_APPROVAL`, `SOURCE_ASSET_MISSING`).
- HVS content-deduplication returns the same `asset_id` for identical sha256; the
  parser accepts dedup PASS output. No-overwrite is HVS-enforced; SCOS never
  overwrites an existing destination.

## 11. Direct Synthetic Acceptance

Synthetic acceptance evidence (real HVS boundary, `hvs8l-...` project):

- Verified HVS project id: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- Required asset: 1 VOICE (project-level, satisfiable via synthetic WAV)
- Optional assets: per-scene VISUAL + MUSIC (not in mandatory gate)
- Source fixture: synthetic operator-owned WAV (no ffmpeg / MP4 / render)
- Full pipeline: reverify → inspect → register → rights → bind → manifest →
  readiness → approval → materialize → verify → render-readiness
- Materialization result: `ok=True`, `status=COMPLETED`
- Per-asset verdict: `PASS`, destination sha256 equals source sha256
- Post-verification: `ok=True`, no missing assets, role/scene binding ok,
  project semantic integrity ok, no render artifact
- Render-readiness: `READY` with `render_authorized=False`,
  `render_started=False`, `render_output_created=False`,
  `render_authorization_required=True`
- HVS `media-readiness` VERDICT: PASS (bound_scenes 0)

## 12. Negative Acceptance

Proven by focused tests and direct acceptance:

- source outside intake root is rejected (`SOURCE_OUTSIDE_ROOT`)
- path traversal / UNC / URL / symlink / null-byte / newline rejected
- unsupported role rejected (`UNSUPPORTED_ROLE`)
- zero-size / non-regular / executable content rejected
- missing rights evidence blocks readiness (`MISSING_RIGHTS`)
- blocking rights status blocks readiness (`RIGHTS_BLOCKERS`)
- readiness not READY blocks approval (`READINESS_NOT_READY`)
- missing materialization confirmation blocks approval
  (`APPROVAL_CONFIRMATION_REQUIRED`)
- missing non-render acknowledgement blocks approval (`NON_RENDER_ACK_REQUIRED`)
- tampered manifest blocks execution (`MANIFEST_CHANGED_AFTER_APPROVAL`)
- changed/removed source blocks execution (`SOURCE_ASSET_CHANGED_AFTER_APPROVAL`,
  `SOURCE_ASSET_MISSING`)
- HVS import failure → `PARTIAL`, not `COMPLETED`
- sha mismatch / verify-failure → `PARTIAL`
- unsafe project id (newline) raises at reverification (no sanitization)
- render is never invoked
- MP4 is never created

## 13. Safety Confirmations

- HVS initializer used: `import-media` (existing boundary only)
- HVS render dispatch used: NO
- Stage 1 adapter `import-media` used: NO (forbidden guard preserved)
- HVS project created by Stage 8M: NO (reuses verified Stage 8L project)
- Assets materialized: YES, operator-owned synthetic voice WAV only, under the
  verified task-owned HVS project
- Exact project id honored: YES
- Source sha256 re-verified before execution: YES
- Post-materialization sha256 matched: YES
- Voice generated by Stage 8M: NO
- Placeholders generated: NO
- Render authorized: NO
- Render started: NO
- MP4 created: NO
- HVS source modified: NO
- HVS commit created: NO
- Customer contacted: NO
- Invoice issued: NO
- Payment link created: NO
- Payment processed: NO
- Network used: NO
- Push performed: NO
- Stage 8K / 8L started by Stage 8M: NO

## 14. Verification Evidence

- Focused Stage 8M tests:
  `.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_production_asset_intake_materialization.py -q -p no:cacheprovider`
  -> 199 passed, 1 skipped (the skipped test is the real-HVS integration
  cluster `TestHVSMaterializationReal`, run explicitly below)
- Real-HVS integration acceptance (explicit):
  `.venv\Scripts\python.exe -m pytest "scos\control_center\tests\test_hvs_production_asset_intake_materialization.py::TestHVSMaterializationReal" -q -p no:cacheprovider`
  -> 8 passed
- Control Center full suite:
  `.venv\Scripts\python.exe -m pytest scos\control_center\tests -q -p no:cacheprovider`
  -> 1523 passed, 2 skipped
- Security scan:
  `.venv\Scripts\python.exe scripts\security_scan_baseline.py`
  -> 471 files scanned, 0 findings, PASS
  (Stage 8M service added to the control-center subprocess allowlist with the
  same safe-pattern rationale as `hvs_adapter.py` / `hvs_render_dispatch.py`)
- Scanner tests:
  `.venv\Scripts\python.exe -m pytest scripts\tests\test_security_scan_baseline.py -q -p no:cacheprovider`
  -> passed
- Collection:
  `.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider`
  -> 1755 tests collected, 0 collection errors
- Direct acceptance: PASS
- Negative acceptance: PASS
- `git diff --check`: exit 0

## 15. Runtime Hygiene

SCOS runtime:

- Stage 8M tracked intake data stored under ignored
  `scos/work/hvs_production_asset_intake`.
- Test fixtures use ignored `tmp_path` (pytest) and the locked intake root.
- No SCOS runtime JSON/JSONL is staged for commit.

HVS runtime:

- HVS tracked status after acceptance: clean
- HVS `git diff --check`: clean
- Task-owned project ignored by HVS `.gitignore`
- Stage 8M materialized operator-owned voice WAV assets only; no MP4, no render,
  no placeholders.

## 16. Known Warnings

- Pytest warns about unknown config option `cache_dir` in the SCOS pytest
  configuration.
- Pytest warns about the unregistered `integration` mark used by the
  real-HVS integration cluster (intentional; run explicitly, not in default
  suite).
- `test_full_suite` (legacy) shells out and may emit a benign
  `UnicodeDecodeError` in a subprocess reader thread on non-UTF8 output; it does
  not affect results.

## 17. Commit Scope

Approved Stage 8M paths:

- `scos/control_center/hvs_production_asset_models.py`
- `scos/control_center/hvs_production_asset_store.py`
- `scos/control_center/hvs_production_asset_service.py`
- `scos/control_center/tests/test_hvs_production_asset_intake_materialization.py`
- `scos/control_center/cli.py`
- `scripts/security_scan_baseline.py`
- `docs/certification/SCOS-HVS-Integration-Stage-8M-production-asset-intake-materialization.md`

No runtime JSON/JSONL, temporary payload, HVS runtime project, HVS source,
customer data, payment evidence, media, assets, MP4, generated artifact, or
Stage 8K/8L code is in scope beyond the listed files.

## 18. Final Verdict

PASS - Stage 8M implementation and certification evidence are complete pending
the authorized local SCOS commit and post-commit verification.
