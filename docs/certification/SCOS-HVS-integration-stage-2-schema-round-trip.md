# SCOS–HVS Integration — Stage 2: Deterministic Schema Mapping & Round-Trip Contract

**Certification document — Stage 2 of the SCOS ↔ Hermes Video Studio (HVS) cross-project integration.**
**Contract grouping:** v2.3 — Cross-Project Contract Foundation.
**Status:** CLOSED (certified).

---

## 1. Objective

Create a **versioned, deterministic translation contract** between SCOS and Hermes Video
Studio, implemented as a **pure translation layer** (no subprocess, no filesystem write,
no network, no HVS import, no rendering, no project creation). The layer:

1. Converts a supported SCOS render request / edit timeline into an HVS-compatible
   project/timeline payload.
2. Validates the produced payload against the actual HVS schema contract.
3. Reconstructs an equivalent SCOS representation from the HVS-compatible payload.
4. Proves semantic equivalence through round-trip tests.
5. Preserves IDs, scene order, timing, dimensions, FPS, asset references, captions, and
   deterministic identity.
6. Rejects unsupported or ambiguous data explicitly.

**Scope boundary:** SCOS model → pure deterministic mapper → versioned adapter payload →
HVS-compatible JSON structure → validation → reverse mapping → semantic comparison.
**Not in scope:** creating HVS projects, copying assets, invoking HVS CLI mutation, rendering.

---

## 2. SCOS Starting Hash & HVS Baseline Hash

| Item | Value |
|------|-------|
| SCOS root | `C:\Workspace\super-creator-os` |
| SCOS branch | `main` |
| SCOS starting HEAD (before Stage 2 commit) | `13fdae4` — `feat(control-center): add HVS adapter dry-run contract` |
| SCOS working tree before Stage 2 work | clean (verified in Phase 0) |
| HVS root | `C:\Workspace\hermes-video-studio` |
| HVS branch | `main` |
| HVS certified baseline | `8c0708d71f92ed5a417ce6ee678ae28f76c39944` |
| HVS working tree | clean (verified before, during, and after — Phase 10 & 15) |
| Python interpreter | `C:\Workspace\super-creator-os\.venv\Scripts\python.exe` (Python 3.11.15) |

---

## 3. Stage 1 Prerequisite Evidence

Stage 1 was confirmed fully closed before Stage 2 work began:

- **Stage 1 adapter production file:** `scos/control_center/hvs_adapter.py`
  (`HermesVideoStudioAdapter`, `frozen=True` dataclass; read-only capability probe;
  `subprocess.run(..., shell=False)`; bounded stdout/stderr; `timeout=`; normalized
  `AgentAdapterResult`; **no** default-renderer change; **no** schema mapping; **no** real
  rendering).
- **Stage 1 adapter tests:** `scos/control_center/tests/test_hvs_adapter.py`
  (37 passed as part of the Stage 1 regression run).
- **Stage 1 certification document:** `docs/certification/SCOS-HVS-integration-stage-1-adapter-scaffold.md`.
- **Stage 1 committed & clean:** HEAD `13fdae4` was committed and the working tree was
  clean at Phase 0 preflight (no staged files, `HEAD == origin/main` left-count `0`/right
  `2` ahead — the authorized Stage 1 closure state; **no push**).

Stage 1 regression was re-run during Stage 2 verification and **passed** (see §7).

---

## 4. SCOS Source-Model Summary

Inspected (read-only) SCOS source:

- `scos/render/base.py` — `RenderRequest` / `RenderClip` (bare path + duration models;
  the only timeline-ish primitives previously in the repo). **No** scene / caption /
  asset-reference / render-preset / edit-timeline model existed.
- `scos/agents/scene_planner.py` — plain-`dict` scene plan; **no** typed model.
- `scos/control_center/hvs_adapter.py` — Stage 1 read-only adapter (unchanged semantics).
- `scos/control_center/agent_adapter_models.py` — `AgentAdapterResult` / `AgentAdapterError`
  (`frozen=True`, `ok`/`metadata`/`error_kind`/`error_detail`/`failed_step`/`request_id`/
  `schema_version`).
- `scos/control_center/credential_redaction.py` — secret redaction utility (not used by
  the mapper; no secrets involved).
- `scos/control_center/__init__.py` — package export conventions.

**Conclusion:** There was **no pre-existing canonical SCOS edit-timeline / scene / caption /
asset / preset model** to duplicate. Per the task directive *"Do not invent duplicate SCOS
models when existing models are sufficient"* — since none were sufficient, the canonical
SCOS input model is **defined here** as `SCOSRenderTimelineProject` (with `SCOSScene`,
`SCOSCaption`, `SCOSAssetRef`) inside the Stage 2 contract module. This is the SCOS-side
representation of a render request / edit timeline that the mapper consumes, and it is the
authoritative SCOS model for cross-project contract work going forward.

### SCOS model field rules (defined in `hvs_contract_models.py`)

| Field | Rule |
|-------|------|
| `project_id` | required, non-empty |
| `run_id`, `request_id` | optional volatile correlation IDs (excluded from deterministic identity) |
| `scene_id` | required, non-empty, unique per project |
| `order` | required, 0-based, unique (no dict-key ordering) |
| `start_ms` | integer ms, `>= 0` |
| `duration_ms` | integer ms, `> 0` |
| `end_ms` | derived `start_ms + duration_ms`; must be `> start_ms` |
| total duration | `sum(duration_ms)` of scenes (contiguous; gaps preserved, not silently clamped) |
| `width` / `height` | positive integers; mapped to HVS resolution enum |
| `fps` | enum member `{24, 25, 30, 60}` |
| asset reference | logical `asset_id` + `asset_type`, optional `asset_path` (path semantics only) |
| caption | `scene_id` + `text` + `start_ms`/`end_ms` (must fall within the scene) |
| `selected_preset` | explicit preset table (see §11) |
| `metadata` | `tuple[tuple[str,str], ...]` optional extension metadata (forward-compatible) |

---

## 5. HVS Schema Summary (read-only inspection)

Read from `C:\Workspace\hermes-video-studio` (HEAD `8c0708d…`), **not modified**:

- `hvs/schemas/project.schema.json`, `hvs/schemas/timeline.schema.json`,
  `hvs/schemas/scene.schema.json`, `hvs/schemas/render_preset.schema.json`,
  `hvs/schemas/caption_style.schema.json`, `hvs/schemas/asset_plan.schema.json`.
- `hvs/core/timeline_models.py` — seconds float, `round(x, 3)`, hash `sha256(...).hexdigest()[:16]`,
  `MIN_SCENES=3, MAX_SCENES=10`.
- `hvs/core/util.py` — `deterministic_hash` excludes `source_agent`, `stage`, `status`,
  `created_at` from the semantic identity.

### Authoritative HVS contract (from JSON schema)

- **Required top-level:** `project_id`, `artifact_id`, `schema_version`, `deterministic_hash`,
  `resolution`, `fps`, `duration_seconds`, `scene_count`, `scenes`.
- **`resolution` enum:** `{"1080x1920", "1920x1080", "1080x1080"}`.
- **`fps` enum:** `{24, 25, 30, 60}`.
- **`scene_count`:** integer **3..6** (timeline.schema.json `minimum`/`maximum`).
  > **Discrepancy noted:** `hvs/core/timeline_models.py` states `MIN_SCENES=3, MAX_SCENES=10`.
  > The **authoritative read-only contract is the JSON schema**, so Stage 2 enforces **3..6**
  > (test `test_scene_count_bounds` covers both bounds). This is a known HVS-internal
  > inconsistency; it does not block Stage 2 because the JSON schema is the validated contract.
- **Scene required:** `scene_id`, `start_time` (≥0), `end_time` (≥0), `duration` (>0),
  `intent`, `visual_description`, `text_overlay`, `asset_slots`, `transition`, plus the
  standard audit block (`schema_version`, `artifact_id`, `project_id`, `created_at`,
  `stage`, `status`, `source_agent`, `deterministic_hash`).
- **Asset slot:** `slot_id`, `scene_id`, `slot_type`, `accepted_formats`, `mock_asset_ref`,
  `asset_path` (optional).
- **Caption style:** `caption_id`, `scene_id`, `text`, `start_time`, `end_time`,
  `font_size`, `position`, `color`.
- **Render preset:** `preset_id`, `quality`, `speed`, `aspect_ratio`.
- **Deterministic hash:** `sha256(semantic_parts).hexdigest()[:16]`.
- **Unknown-field policy:** HVS payloads use `additionalProperties: true`, so unknown
  *optional* metadata is accepted; required *semantic* fields missing → rejected.
- **Schema version:** `hvs/schemas` uses `1.0.0`.

---

## 6. Complete Field-Mapping Table

SCOS → HVS (forward). Reverse (HVS → SCOS) uses the same semantic core stored under the
`x_scos` extension block so the round trip is lossless.

| SCOS field | HVS field | Transformation | Reverse | Validation | Unsupported behavior |
|------------|-----------|----------------|---------|------------|----------------------|
| `project_id` | `project_id` | direct | direct | non-empty | missing → `missing_required_field` |
| `run_id` | (volatile, not mapped) | excluded | — | — | — |
| `request_id` | (volatile, not mapped) | excluded | — | — | — |
| `scene_id` | `scenes[].scene_id` | direct | direct (x_scos) | non-empty, unique | dup → `duplicate_scene_id` |
| `order` | `scenes[].order` (x_scos) | direct | direct | unique, 0-based | dup → `duplicate_order_index` |
| `start_ms` | `start_time = start_ms/1000` (round 3) | ms→s | ×1000 round | `>= 0` | `<0` → `negative_start` |
| `duration_ms` | `duration = duration_ms/1000` (round 3) | ms→s | ×1000 round | `> 0` | `0` → `zero_duration` |
| `end_ms` | `end_time = end_ms/1000` (round 3) | derived | derived | `> start` | `<= start` → `end_before_start` |
| total duration | `duration_seconds = Σduration` | sum ms→s | Σ ms | `> 0` | — |
| `width`/`height` | `resolution = "{w}x{h}"` | format | parse ints | in enum | not in enum → `unsupported_resolution` |
| `fps` | `fps` | direct | direct | in enum | not in enum → `unsupported_fps` |
| `asset_id` | `asset_slots[].slot_id` + `mock_asset_ref` | direct | direct (x_scos) | — | — |
| `asset_type` | `asset_slots[].slot_type` | direct | direct | — | — |
| `asset_path` | `asset_slots[].asset_path` | normalize `\\`→`/` | stored | no `..` traversal | `..` → `path_traversal` |
| caption `text` | `caption_style[].text` (x_scos) | direct | direct | — | — |
| caption `start_ms/end_ms` | `caption_style[].start/end_time` | ms→s | ms | within scene | out → `caption_out_of_scene` |
| `selected_preset` | `x_scos.selected_preset_hvs` | preset table | preset table | in table | not in table → `unsupported_preset` |
| `metadata` | `x_scos.metadata` | direct | direct | — | — |
| (derived) `artifact_id` | `artifact_id` | `hvs_artifact_id(project_id, scene_count)` | direct | non-empty | — |
| (derived) `deterministic_hash` | `deterministic_hash` | sha256[:16] of semantic core | direct | — | — |
| `schema_version` | `schema_version` | `1.0.0` | direct | equals `1.0.0` | mismatch → `schema_version_mismatch` |

**Transformation rules (canonical timing unit):** integer milliseconds internally; HVS
boundary uses seconds with `round(x, 3)`. No raw binary float enters the deterministic
identity. **Floating-point comparison is avoided** by converting back to integer ms for the
round-trip equality check (`round(sec*1000)`).

---

## 7. Transformation Rules Detail

- **SCOS → HVS** produces the *full plan shape* that the HVS schema actually validates
  (project + timeline + scenes + render_preset + caption_style + asset_plan). The SCOS-only
  semantic core is preserved verbatim under `x_scos` so reverse mapping is exact.
- **HVS → SCOS** reads the HVS fields (for compatibility) and the `x_scos` block (authoritative
  SCOS reconstruction), reconstructing `SCOSRenderTimelineProject` with identical scenes,
  captions, asset refs, preset, and metadata.
- **Validation** (`validate_hvs_payload`) checks every required HVS top-level and per-scene
  field, enum membership, scene_count bounds, non-overlap, positive timing, and reports
  structured `MappingIssue` entries (no silent drops).
- **Reverse-mapping behavior:** identical semantic fields reconstructed; volatile IDs and
  audit fields are not reconstructed as SCOS input.

---

## 8. Canonical Timing Unit

**Integer milliseconds** for all SCOS-internal timing. HVS boundary = seconds, `round(x, 3)`.
Round-trip timing difference = **0 ms** (verified by `test_round_trip_equivalent` and
`test_reverse_preserves_total_duration`). No silent duration clamp; gaps preserved (policy:
contiguous plan duration = Σ scene durations; gap retained in `start_ms` and round-trips
exactly).

---

## 9. Resolution / FPS Rules

- `width`/`height` must be positive integers and combine to a HVS resolution enum member;
  otherwise `unsupported_resolution`.
- `fps` must be in `{24, 25, 30, 60}`; otherwise `unsupported_fps`.
- Orientation is taken **literally** from `width x height` (no inference). No default
  substitution.

---

## 10. Asset-Reference Rules

- Logical `asset_id` is the deterministic identity; filesystem path is **not** required to
  exist during pure mapping.
- `asset_type` preserved as `slot_type`.
- Path separators normalized `\\` → `/` only when a path is provided (path semantics are
  part of the contract).
- **Parent-directory traversal (`..`) is rejected** (`path_traversal`) — paths never affect
  the deterministic hash; the hash is over `asset_id` + `asset_type` only.
- No machine-specific absolute paths are placed in the deterministic hash.

---

## 11. Caption Rules

- `text` preserved exactly (Unicode-safe; tested with Thai / Chinese / emoji / Devanagari).
- `scene_id` association preserved.
- `start_ms`/`end_ms` preserved; must fall within the associated scene
  (`caption_out_of_scene` otherwise).
- Order preserved (stable per scene). No silent whitespace trimming of meaningful content.

---

## 12. Preset Mapping Table

| SCOS preset | HVS preset | Supported |
|-------------|------------|-----------|
| `draft` | `draft` | ✅ |
| `standard` | `standard` | ✅ |
| `fast` | `fast` | ✅ |
| (any other) | — | ❌ `unsupported_preset` |

HVS also defines `high_quality`, but SCOS has no matching preset; it is intentionally **not**
mapped (no silent fallback).

---

## 13. Contract Version

- `SCOS_HVS_TIMELINE_CONTRACT_ID = "scos-hvs.timeline.v1"`.
- `SCOS_HVS_SCHEMA_VERSION = "1.0.0"` (aligned with HVS JSON schema version).
- Stored in every payload under `x_scos.contract_id` / `x_scos.contract_version` and asserted
  by `validate_hvs_payload`.

---

## 14. Canonical Serialization

- `SCOSRenderTimelineProject.to_dict()` → ordered `dict`; `to_hvs_payload()` reuses the
  mapper's forward path.
- `canonicalize_mapping_payload()` returns a JSON-string-serializable, key-order-independent
  representation (`json.dumps(payload, sort_keys=True, ensure_ascii=False)`) for hashing and
  comparison.

---

## 15. Deterministic Hash Inputs

`payload_identity_hash(payload)` = `sha256(canonical_semantic_core).hexdigest()[:16]` where
the semantic core is built from **sorted** items:
`project_id`, `artifact_id`, `resolution`, `fps`, `duration_seconds`, `scene_count`,
per-scene (`scene_id`, `order`, `start_time`, `duration`, `intent`, `visual_description`,
`text_overlay`, `transition`, `asset_slots`, `captions`), `render_preset`, and
`x_scos.metadata`.

**Excluded volatile values:** `run_id`, `request_id`, the HVS audit block
(`source_agent`, `stage`, `status`, `created_at`), and `schema_version` (version is a
contract marker, not semantic content).

**Properties verified (tests 28–34, 43):**
- identical semantic input → identical hash;
- dict-key ordering does not change the hash;
- volatile metadata does not change the hash;
- changing timing / asset / caption / resolution / fps **changes** the hash;
- Windows vs POSIX path formatting does not change the hash (path not in identity).

---

## 16. Reverse-Mapping Behavior

`map_hvs_to_scos(payload)` returns `HVSMappingResult` with `.payload_model`
(`SCOSRenderTimelineProject`). It reads the HVS fields and the `x_scos` block, reconstructs
scenes/captions/asset-refs/preset/metadata, and validates the inverse. Missing or malformed
required fields → `missing_required_field` / `invalid_scene_count` etc.

---

## 17. Round-Trip Equivalence Policy

`compare_round_trip(scos_project)` runs forward then reverse and compares:
`project_id`, `width`, `height`, `fps`, `total_duration_ms`, `selected_preset`,
scene order/IDs/timing, per-scene captions (text + timing), per-scene asset refs
(id + type + path), and metadata. A zero-length `diffs` tuple ⇒ `equivalent = True`.
**Canonical-unit (ms) comparison avoids floating-point inequality.**

---

## 18. Unsupported-Field Behavior

- Unknown **optional** metadata (HVS `additionalProperties: true`) is preserved under
  `x_scos.metadata` and ignored for identity.
- Unknown **required** semantic field (e.g. deleting a required HVS key) →
  `validate_hvs_payload` returns `ok=False` with a structural issue (`test_27`).
- No unknown field is silently dropped, clamped, or defaulted.

---

## 19. Files Created / Modified

| File | Status | Purpose |
|------|--------|---------|
| `scos/control_center/hvs_contract_models.py` | **created** (463 lines) | Versioned contract models: `SCOSRenderTimelineProject`, `SCOSScene`, `SCOSCaption`, `SCOSAssetRef`, `HVSPayloadIssue`/`HVSMappingResult`, enums/constants. |
| `scos/control_center/hvs_schema_mapper.py` | **created** (886 lines) | Pure mapper: `map_scos_to_hvs`, `map_hvs_to_scos`, `validate_hvs_payload`, `compare_round_trip`, `canonicalize_mapping_payload`, `payload_identity_hash`. |
| `scos/control_center/tests/test_hvs_schema_mapper.py` | **created** (609 lines) | 47 focused contract tests (all 45+ required cases). |
| `scos/control_center/hvs_adapter.py` | **modified** (narrow) | Added `HermesVideoStudioAdapter.plan_hvs_contract_payload(...)` — a **planning-only** method that delegates to the pure mapper and returns an `AgentAdapterResult`/`AgentAdapterError`. **No activation change, no subprocess, no HVS write, no renderer change.** |

No `control_center/__init__.py` change was needed (the mapper is imported explicitly by name
in tests and by the adapter method).

---

## 20. Test Evidence

### Focused mapper tests
`scos/control_center/tests/test_hvs_schema_mapper.py` → **47 passed**.
Covers: valid minimal map, multi-scene order, ID preservation, timing in canonical ms, total
duration, resolution/FPS, asset refs/types, caption text/timing, Unicode round-trip, preset
map/exact, unsupported preset fail, missing project/scene field fail, negative start fail,
zero duration fail, end-before-start fail, duplicate scene ID / order fail, unsupported FPS
fail, invalid resolution fail, scene overlap rejected, gap preserved, unknown optional
metadata preserved, unknown required field fail, identical-payload, key-order hash stability,
volatile-metadata hash stability, timing/asset/caption/res-fps hash change, round-trip
equivalence, input-not-mutated, no-subprocess, no-filesystem-write, no-HVS-import,
Stage-1-readonly-unchanged, default-renderer-unchanged, no-HVS-project-created,
Windows-path-determinism, path-traversal-rejected, contract-version-present,
cross-repo-HVS-schema-readonly, caption-out-of-scene-rejected, scene-count-bounds,
reverse-preserves-total-duration, canonicalization-key-order-independent.

### Stage 1 regression tests
`scos/control_center/tests/test_hvs_adapter.py` + `test_agent_adapter_models.py` →
**37 passed** (re-run during Stage 2 verification; Stage 1 adapter semantics unchanged).

### Control Center suite
`scos/control_center/tests` → **711 passed, 0 failed** (includes the 47 focused + 37 Stage 1
regression). One benign warning: `pytest.PytestUnhandledThreadExceptionWarning` from a
background subprocess reader — **not suppressed** (per task instruction).

### Full SCOS suite
`pytest` (repo-wide) → **1141 passed, 0 failed, 1 warning**, elapsed ≈ 32 min 49 s.
Collection clean (0 errors). No test reduction vs the authoritative committed baseline
(1063 at Stage 0; increased by Stage 1 and Stage 2).

### Smoke
`scripts/test_smoke.py` → **16 passed, 0 failed**.

### Security
`scripts/security_scan_baseline.py` → **392 files scanned, 0 findings, PASS**.
The +5 files vs the Stage 0 baseline (387) are exactly the new/modified Stage 2 files
(production + tests + `__pycache__`); none were flagged because the mapper contains no
subprocess / network / runtime-write patterns and the test file's side-effect checks use
source-level AST inspection (no global monkeypatch).

---

## 21. Cross-Repository Evidence

- **HVS schemas read:** `project`, `timeline`, `scene`, `render_preset`, `caption_style`,
  `asset_plan` JSON schemas (read-only).
- **HVS baseline (start → end):** `8c0708d71f92ed5a417ce6ee678ae28f76c39944` → unchanged.
- **HVS working tree (start → end):** clean → clean (`git status --porcelain=v1 -uall` empty
  both times; `git diff --check` clean).
- **No files created** in HVS (project dir count unchanged at 1874 pre-existing entries).
- **No CLI mutation / render:** the mapper imports no HVS internals and invokes no HVS CLI;
  the only HVS subprocess use remains the Stage 1 read-only capability probe.
- **Cross-repo schema test (`test_cross_repo_hvs_schema_readonly`)** reads
  `hvs/schemas/timeline.schema.json` read-only, asserts authoritative `scene_count` 3..6 and
  resolution enum, and validates a produced payload against the required-field set — without
  writing into HVS.

---

## 22. Scope Confirmation

- ✅ No HVS modification (read-only inspection only).
- ✅ No HVS project creation.
- ✅ No rendering (real or dry-run).
- ✅ No default-renderer change (`RenderProfile` untouched; `hvs_adapter.py` contains no
  `VideoUse`/`renderer` reference).
- ✅ No asset copy.
- ✅ No approval-token propagation.
- ✅ No A/V-sync / quality / memory / commercial integration.
- ✅ No UI or API work.
- ✅ No network access (no `requests`/`urllib`/`socket`/`httpx`/`aiohttp`).
- ✅ No package installation / dependency or lock-file change.
- ✅ No push / pull / fetch / deploy / publish.
- ✅ No repository consolidation.

---

## 23. Certification

**Document path:** `docs/certification/SCOS-HVS-integration-stage-2-schema-round-trip.md`

**Readiness verdict:** ✅ **PASS — Integration Stage 2 CLOSED.**
The SCOS–HVS deterministic schema mapping and round-trip contract are certified and ready
for Stage 3 approval-gated project creation.

**Known limitations:**
1. HVS `timeline.schema.json` `scene_count` is 3..6 while `hvs/core/timeline_models.py`
   allows 3..10. Stage 2 honors the **JSON schema** (authoritative). If HVS later relaxes the
   schema to 3..10, the mapper bound should be revisited.
2. The SCOS→HVS payload is the *full plan shape*; only SCOS→HVS and HVS→SCOS translation +
   validation are implemented. Actual HVS project creation / rendering is explicitly **out of
   scope** for Stage 2 (Stage 3).
3. `high_quality` HVS preset is unmapped (no SCOS equivalent); no fallback.
4. `caption_style` color/font defaults are HVS-side; SCOS does not yet model caption styling
   beyond text + timing.

**Rollback procedure:**
- The change is a single local SCOS commit (no push). To roll back:
  `git revert <stage2-commit>` or `git reset --soft <stage1-head>` (operator-authorized only),
  then re-run `pytest scos/control_center/tests/test_hvs_schema_mapper.py` to confirm removal.
- HVS requires no rollback (unchanged, clean).

---

## 24. Final Report Summary (for operator)

- **VERDICT: PASS** — Integration Stage 2 CLOSED.
- SCOS `13fdae4` (start) → one new commit (see Stage 15).
- HVS `8c0708d71f92ed5a417ce6ee678ae28f76c39944` unchanged, clean.
- Focused: 47 passed · Stage 1 regression: 37 passed · Control Center: 711 passed ·
  Full SCOS: 1141 passed · Smoke: 16 passed · Security: 392 files / 0 findings.
- No subprocess, no file write, no HVS import, no mutation, no render, no project creation,
  no renderer change.
