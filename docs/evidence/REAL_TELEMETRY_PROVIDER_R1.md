# Real Telemetry Provider R1 — Evidence Seal

## Scope

This checkpoint adds the first real platform observation route without creating a
parallel telemetry store or learning subsystem.

Implemented:

- `integrations/learning/observation_binding.py` — verifies render provenance and
  current artifact bytes before an observed row can be bound.
- `integrations/learning/youtube_analytics_adapter.py` — OAuth bearer adapter for
  the official YouTube Analytics reports API.
- `integrations/learning/validators.py` — API observations require evidence fields.
- `integrations/learning/telemetry.py` — rejects cross-artifact/graph evidence conflicts
  for the same `loop_run_id` and surfaces observed evidence through the causal join.
- `integrations/learning/tests/test_real_telemetry_adapter.py` — provider and evidence
  verification.
## Evidence contract

API telemetry must bind:

`loop_run_id` + `graph_fingerprint` + `artifact_sha256` + `platform_content_id`.

The render provenance is re-read and the output file SHA-256 is recomputed before
ingestion. A mismatch fails closed. The provider query and selected response row are
also fingerprinted with SHA-256 for reproducibility without storing OAuth secrets.

## Provider route

`premium render provenance -> verified binding -> YouTube Analytics API -> canonical
observed row -> existing telemetry sidecar -> existing causal join -> learning evaluator`

OAuth access is supplied through `SCOS_YOUTUBE_ANALYTICS_ACCESS_TOKEN`; credentials
are never persisted into telemetry evidence or passed as CLI arguments.
## Verification

- Learning suite: **54 passed**.
- Premium Media focused suite: **22 passed**.
- Targeted telemetry/provider suite: **18 passed**.
- Python compileall: passed.
- `git diff --check`: passed.

## Current truth boundary

Implementation and mocked/provider-contract verification are complete.
Real platform observation is NOT claimed by this checkpoint because it requires
authorized YouTube OAuth access and a real published platform content ID.
No external publish or Human Publish Gate is performed by this change.
