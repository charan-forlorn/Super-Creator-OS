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
