# Skill: scos-production-loop

## Purpose
Close one SCOS production run deterministically: reconcile current task truth, seal the produced media artifact, stage a content-addressed clip, record truthful telemetry state, and seal evidence.

## When to Use
- After a production render completes and before reporting the run complete.
- When the same run is being retried and rerun overhead must be minimized.
- When artifact, staging, telemetry, and evidence need one canonical closure receipt.

## Core Rules
- The deterministic executor is `scos/control_center/production_loop_capability.py`.
- It is local-first and never publishes, dispatches, calls external APIs, or infers Human approval.
- Artifact identity is SHA-256 based; staged bytes must match the source hash.
- Generated `scos/work/` and `evidence/production-loop/` outputs are excluded from their own Git truth fingerprint.
- Missing production telemetry remains an explicit open data gate; never fabricate an observation.
- A changed input invalidates the previous sealed evidence bundle.

## How to Run

Use the Hermes terminal tool from the SCOS repository root:

```text
python scripts/scos_production_loop.py --task-id <task-id> --run-id <run-id> --artifact <repo-relative-mp4>
```

Optional observed telemetry:

```text
--telemetry-export <csv-or-json>
--telemetry-db <database-json>
--telemetry-path <telemetry-json>
--source manual|api
```

## Required Output
- Task reconciliation state and current Git fingerprint.
- Artifact SHA-256, size, and FFprobe media contract.
- Deterministic staged clip path and byte identity.
- Telemetry status: joined, orphan, blocked, or open.
- Evidence bundle ID, seal SHA-256, and stale-evidence invalidation record when applicable.

## Procedure
1. Run the deterministic CLI once for the target run.
2. Treat non-zero exit as BLOCKED; inspect the emitted reason before retrying.
3. When status is `SEALED_WITH_OPEN_TELEMETRY`, continue the engineering loop but do not claim a real production observation.
4. Re-running unchanged inputs should reuse the staged clip and reproduce the same evidence bundle ID.
5. A changed artifact, Git truth input, or telemetry receipt must produce a new fingerprint and invalidate the previous bundle.

## Boundaries
- Human publication, external dispatch, credential handling, and financial actions remain outside this capability.
- Telemetry receipt binding may write observed telemetry through the existing canonical learning path, but learning qualification remains governed separately.
- This skill does not replace HAIOS authority, approval gates, or the existing Control Center state/evidence authorities.

## Verification
Run the focused capability tests:

```text
python -m pytest scos/control_center/tests/test_production_loop_capability.py -q
```

For a real production artifact, verify the JSON receipt, staged file SHA-256, and evidence seal on disk after the CLI exits.

## Resource-Aware Generation Guard
Before a new local generative render, use the provider's resource-aware execution path. The Wan VACE worker selects `cpu_offload` automatically below 12 GB VRAM and adaptively caps the generation long edge to 480 px while preserving aspect ratio. The worker emits effective resolution and peak VRAM telemetry. Do not bypass the policy by forcing direct CUDA on an 8 GB-class machine unless explicitly benchmarking or debugging under a bounded test run.

## Anti-Rerun Rule
Do not rerun the capability when artifact bytes, Git truth, telemetry inputs, and evidence state are unchanged. Use the existing sealed receipt as the current truth.


## External Platform Telemetry Guard
The read-only external observation path is scripts/scos_external_telemetry.py backed by
integrations/learning/youtube_api_telemetry.py for YouTube Analytics v2.
It queries measured platform metrics only, maps them to source=api, and routes writes through
telemetry_capture.capture and the existing telemetry receipt/validation moat.
OAuth material must come from an explicit environment variable or caller-owned token provider;
SCOS never persists or prints token material. Missing authorization fails closed as
YOUTUBE_ANALYTICS_AUTH_REQUIRED before network access. This path never publishes or dispatches.
The current host has no YouTube/Google credential configured, so the production telemetry gate
remains open until a Human-controlled publish/auth setup yields a real platform video ID and API observation.


## OAuth Runtime Boundary
YouTube Analytics authorization now uses an installed-app OAuth 2.0 PKCE + loopback flow.
The required read-only scopes are `https://www.googleapis.com/auth/youtube.readonly` and
`https://www.googleapis.com/auth/yt-analytics.readonly`. The short-lived access token is held
in memory; the refresh token is encrypted with Windows DPAPI under the current Windows user.
The external telemetry CLI prefers the DPAPI store when no explicit access-token environment
variable is supplied. Never print, commit, or place OAuth token material in evidence.
