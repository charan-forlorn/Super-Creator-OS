# HVS Replacement & Real Telemetry Routes — 2026-09-10

## Purpose

Close the recoverable engineering work without fabricating production evidence or
reviving an unverified dependency. Preserve the current fail-closed contracts.

## R5 — Real telemetry route

The existing SCOS learning layer already provides an observed-only telemetry store
and capture layer. `telemetry_capture.py` rejects prediction-derived fields and
requires `source` to be `manual` or `api`; `telemetry.py` performs lock-protected,
append-only, atomic persistence and joins rows to provenance using `loop_run_id`.

The missing piece is a real provider adapter. The production architecture should be:

`platform API/export -> provider adapter -> canonical observed schema -> telemetry.json`

YouTube is the strongest first adapter because the official Analytics API exposes
views, engagedViews, averageViewDuration, averageViewPercentage, likes, comments,
shares and subscribersGained for authorized channel/video reporting.

TikTok should use the authenticated creator/user API path for owned content. TikTok's
Research API is intended for qualifying research access and is not a substitute for
commercial creator analytics; its archived public-content data can also lag current
counts.

Instagram should use the authorized Meta/Instagram Insights path where the account
and app permissions provide the needed media metrics; otherwise use exported
platform analytics. Every ingest must retain collection timestamp and source.

M1/M2 remain blocked until at least one real published artifact produces an observed
row that causally joins to a real `loop_run_id`.

## R9 — HVS replacement

The old HVS repository is absent from the canonical Workspace and no trusted
Hermes/NousResearch HVS repository was found in GitHub search. The old path is
therefore treated as an unrecoverable legacy dependency rather than recreated.

Do NOT make a recovery snapshot masquerade as `C:\Workspace\hermes-video-studio`.

Use the installed HyperFrames 0.7.45 stack as the canonical local video engine.
The local installation passes its version/doctor checks and already has the valid
FFmpeg, FFprobe, Chrome and Docker dependencies required by its local workflow.

Architecture target:

`SCOS video contract -> engine adapter -> HyperFrames`

HVS becomes an optional legacy adapter, enabled only when a verified canonical HVS
repository is explicitly configured. Materialization tests must target the adapter
contract and safety invariants, not a guessed filesystem path.

## Safety gate

This document does not fabricate telemetry, credentials, authority grants, or HVS
repositories. External owner actions remain outside the code-only closure boundary.

## 2026-09-10 execution update

- HAIOS and SCOS route documents were pushed to their canonical remotes.
- Upstream HyperFrames has advanced beyond the 0.8.31 release during this execution; npm currently resolves `0.8.33`, while the GitHub release feed confirms the v0.8.x line is actively maintained. Local integration remains pinned at `0.7.45` pending controlled dependency upgrade and focused verification.
- No canonical Hermes Video Studio repository was found locally or in trusted GitHub search, so the old dependency is treated as unrecoverable.
- Real telemetry remains evidence-gated: the architecture is ready, but no production observation is fabricated.

## Current upstream verification

HyperFrames upstream reports `v0.8.31` as the latest release on 2026-09-07. The repository describes HyperFrames as an open-source deterministic HTML/CSS/media-to-video framework for local use and AI coding agents.

The local `scos-hyperframes-0.7.45` installation is healthy for the core local toolchain: HyperFrames 0.7.45, Node 24.20.0, FFmpeg 8.1.2, FFprobe 8.1.2, Chrome headless, and Docker are detected by `hyperframes doctor`.

## R9 execution closure

The new `video_engine_materialization.py` backend is the default local-first materialization path when `SCOS_VIDEO_ENGINE` is `hyperframes` or when the legacy HVS repository is absent. It writes deterministic project contracts into the server-selected isolated root and performs read-only integrity inspection.

Focused bridge verification: 3 test files, 30/30 tests passed. This closes the former canonical-HVS fixture blocker without recreating or substituting a recovery repository.

## Verification seal

R9 replacement verification completed: Python materialization tests `34 passed`; Control Center integration tests `41 files / 262 tests passed`; security static scan `691 files / 0 findings`.

These results validate the HyperFrames-backed materialization contract and fail-closed safety boundary. They do not claim real HVS execution.

## R5 execution closure update

The exported-analytics fallback is now implemented as `integrations/learning/telemetry_export.py`.
It accepts CSV/JSON platform exports, normalizes common metric aliases, preserves unknown
fields for integrity rejection, and routes every row through the existing observed-only
`telemetry_capture.capture` path. Focused telemetry verification: `13 passed`.

This closes the recoverable ingestion engineering gap. It does not create real observations;
the M1/M2 closure gate remains a real published artifact joined to a provenance-bearing
`loop_run_id`.

## R9 regression alignment

Legacy tests that require the absent canonical HVS checkout/input are now explicitly skipped
with a visible reason instead of failing against a nonexistent path. Replacement-path tests
remain active and green. Full SCOS Python verification after the change: `2411 passed, 21
skipped, 21 deselected`; frontend verification: `41 test files / 262 tests passed`.

The local-first HyperFrames materialization path remains the only default when no verified HVS
checkout is configured. No recovery snapshot is promoted to HVS identity.
