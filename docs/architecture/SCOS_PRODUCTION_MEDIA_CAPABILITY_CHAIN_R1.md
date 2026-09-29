# SCOS Production Media Capability Chain R1

Date: 2026-09-21
Status: TECHNICAL CAPABILITY CLOSURE / PRODUCTION TELEMETRY DATA GATE OPEN

## 1. Render Cache + Incremental Rendering

- Added `scos/render/render_cache.py` as disposable, content-addressed acceleration state.
- Scene cache identity binds source SHA-256, audio SHA-256, render profile, encoder signature, and scene semantics.
- Final cache identity additionally binds the vendored video-use backend source fingerprint.
- Cache hits verify manifest fingerprint and artifact SHA-256 before reuse.
- Invalid cache entries are treated as misses; no silent trust of stale artifacts.
- Real machine benchmark: first render 1.646s; exact final-cache hit 0.043s; 38.38x measured speedup.

## 2. GPU-aware Render Routing

- Added deterministic local encoder discovery in `scos/render/hardware.py`.
- Routing modes: `auto`, `off`, `required`.
- Current machine truth: NVIDIA RTX 5050 Laptop GPU; FFmpeg exposes `h264_nvenc`.
- Current AUTO plan: `nvenc / h264_nvenc / NVIDIA`.
- Direct NVENC probe produced a real output file.
- GPU-required mode fails closed when no supported hardware encoder exists.

## 3. Platform Variants

- Added `scos/render/platform_variants.py`.
- Supported local render profiles: vertical 1080x1920, square 1080x1080, landscape 1920x1080.
- All variants reuse the canonical renderer, cache, and GPU routing.
- A vendor geometry mismatch discovered during E2E was corrected at the SCOS boundary: square output is normalized to 1080x1080 without mutating the vendor engine contract.
- Silence edge case fixed at the vendor integration boundary: non-finite loudnorm measurements now preserve audio unchanged rather than constructing an invalid normalization command.

## 4. Brand / Platform Delivery Planning

- Added `scos/control_center/platform_delivery_plan.py`.
- Plans are deterministic and artifact-SHA bound.
- Supported platform-format vocabulary reuses existing SCOS/HVS format families.
- Plan state is `READY_FOR_MANUAL_PUBLISH` or `BLOCKED`.
- `external_dispatch_allowed=false`; `human_publish_required=true`.
- No Buffer/platform API/network dispatch was introduced.

## 5. Asset Acquisition / Indexing Intelligence

- Added `scos/assets/asset_index.py`.
- Read-only scan with SHA-256 content identity and FFprobe metadata.
- Explicit states: READY, CHANGED, MISSING, UNSUPPORTED, ERROR.
- Bounded by file-count and byte-count budgets.
- Current real `scos/work/assets` scan: 50 indexed media entries, 45 unique SHA-256 identities, 5 duplicate groups, 50 READY entries.
- Indexing does not copy or mutate assets and is not project-state authority.

## 6. Real Telemetry Engineering Boundary

- Existing observed-only telemetry ingestion remains the canonical write path.
- Added `integrations/learning/telemetry_receipt.py` to bind imported observations to existing provenance-bearing `loop_run_id` records.
- Receipt states: `OBSERVATIONS_JOINED`, `ORPHAN_OBSERVATIONS`, or `BLOCKED`.
- Orphan observations never qualify learning.
- The engineering path is verified, but the current machine has no `memory/telemetry.json`; therefore no real production observation is claimed.
- Current `memory/database.json` contains 3 records with provenance-bearing `loop_run_id` values, but zero observed telemetry rows currently join to them.

## 7. Verification

| Subsystem | Result |
|---|---:|
| Render subsystem | 11 passed |
| Asset subsystem | 13 passed |
| Control Center | 2420 passed / 21 skipped / 21 deselected |
| Learning + replay | 66 passed |
| Capability chain targeted suite | 19 passed |
| Telemetry receipt/export | 6 passed |
| Security scan | 437 files / 0 findings |
| Git diff check | PASS |

## 8. Governance

- No production publish was performed.
- No external platform dispatch was added.
- Human approval was not inferred.
- Render cache and asset index are acceleration/read-model layers only.
- Observed telemetry remains evidence-gated until a real published artifact produces a source-authenticated observation joined to a real `loop_run_id`.

## 9. Next dependency-safe value

1. Capture a real platform observation for one existing provenance-bearing `loop_run_id` and close the telemetry data gate.
2. Then wire the observed receipt into the existing AnalyticsReplay/Feedback/Knowledge loop; do not create another analytics engine.
3. Keep durable public ingress and external publishing separate from technical qualification.

## 10. Deterministic Production-Loop Closure

Added `scos/control_center/production_loop_capability.py` and the Hermes-facing CLI
`scripts/scos_production_loop.py` as the mechanical closure path for one production run.

The capability now performs, in one deterministic transaction:

```text
task reconciliation
→ artifact SHA/FFprobe sealing
→ content-addressed clip staging
→ truthful telemetry gate / existing telemetry receipt
→ evidence sealing
→ stale-evidence invalidation
→ final closure receipt
```

Generated work/evidence outputs are excluded from the capability's own Git truth fingerprint,
preventing self-induced stale-evidence loops. Unchanged inputs are idempotent; changed artifact
bytes, Git truth, or telemetry inputs produce a new input fingerprint and invalidate the prior
bundle.

The capability is local-only and does not publish, dispatch, call external APIs, handle secrets,
or infer Human approval. Missing production telemetry remains `SEALED_WITH_OPEN_TELEMETRY`
rather than a fabricated PASS.

Hermes uses the project-local `.skills/scos-production-loop/SKILL.md` as the operator surface;
the Python capability remains the deterministic execution authority.

## 11. Resource-Aware Generative Execution / Stability Guard

Added `integrations/video_generation/resource_policy.py` and wired it into the isolated
Wan VACE worker and SCOS `WanVaceBackend`.

The deterministic policy is:

```text
VRAM < 12 GB
→ CPU model offload
→ adaptive long-edge cap = 480 px
→ preserve aspect ratio with 16-pixel alignment
→ emit load/effective-resolution/peak-VRAM telemetry

VRAM >= 12 GB
→ direct CUDA unless explicitly overridden
```

The policy is explicit in each generated worker job (`load_mode`, `adaptive_resolution`) and
the worker reports `effective_width`, `effective_height`, `peak_vram_mib`, and policy reason.
It is fail-closed for invalid load-mode values.

Real-machine validation on the RTX 5050 Laptop GPU produced a successful SCOS backend run at
`272x480@16`, `cpu_offload`, `adaptive_resolution=true`, `motion_score=0.000165`, with a
250.91 second worker runtime and no new Windows crash/reboot events during the tested run.
The resulting artifact was then passed through the deterministic SCOS finishing and evidence
closure path.

This capability is intended to prevent the renderer from treating an 8 GB GPU as if it had
higher VRAM capacity. It optimizes stability first while retaining higher native resolution
on systems with sufficient VRAM; it does not infer Human approval or production success.


## 12. External Platform Telemetry Activation

SCOS now has a read-only YouTube Analytics v2 observation adapter:
- integrations/learning/youtube_api_telemetry.py
- scripts/scos_external_telemetry.py
- integrations/learning/tests/test_youtube_api_telemetry.py

The operational CLI path is:

```text
YouTube Analytics API
→ video-dimension measured rows
→ YouTubeObservedTelemetryAdapter
→ source=api observed-only export snapshot
→ telemetry_receipt / canonical capture
→ telemetry.json
→ causal join
```

The adapter also exposes a programmatic `collect_and_capture` path for callers that already
own the canonical telemetry write boundary; the CLI deliberately uses export snapshot + receipt
to avoid double-writing observations.

The adapter requests views, comments, likes, shares, subscribersGained,
averageViewDuration, and averageViewPercentage. YouTube's current API documentation
requires authorized requests and documents the video dimension/filter and these metrics. citeturn780511search0turn114650search1turn114650search9

Security/governance boundaries remain explicit: no publish/dispatch, no secret persistence,
no predicted metric ingestion, and no inferred Human approval. The current machine check found
no YouTube/Google credential in environment or the expected local credential locations, so a real
external observation could not truthfully be claimed during this development pass.

The deterministic activation CLI fails closed before network access when its configured token
environment variable is absent. Once a Human-controlled OAuth credential and a real published
video-to-loop_run_id mapping exist, the same CLI can collect the observation without changing
the telemetry storage contract.


## 13. OAuth 2.0 Runtime Activation Boundary

SCOS now has a local installed-app OAuth flow for YouTube Analytics:
- `scripts/scos_youtube_oauth.py`
- `integrations/learning/youtube_oauth_store.py`
- `integrations/learning/youtube_oauth_runtime.py`
- `integrations/learning/tests/test_youtube_oauth.py`
- `integrations/learning/tests/test_youtube_oauth_store.py`
- `integrations/learning/tests/test_youtube_oauth_runtime.py`

The flow uses PKCE and a loopback redirect, opens Google's consent screen in the system browser,
and requires explicit Human consent before credential materialization. Google currently documents
`youtube.readonly` as required for `reports.query`, and `yt-analytics.readonly` as the read-only
Analytics scope. citeturn912111search6turn357547search0

Refresh tokens are stored only after successful authorization and API verification, encrypted with
Windows DPAPI for the current Windows user at `%LOCALAPPDATA%\\SCOS\\credentials\\youtube_analytics.dpapi`.
The access token is refreshed into memory at telemetry runtime and is never written to source or evidence.

Current machine state: OAuth browser flow is active at the Human consent gate; the secure token store
does not yet exist. No publish or dispatch has occurred.
