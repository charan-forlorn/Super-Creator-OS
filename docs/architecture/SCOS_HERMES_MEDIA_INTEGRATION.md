# SCOS ↔ Hermes Media Integration

SCOS owns deterministic media truth. Hermes owns orchestration and operator intent.
The boundary is JSON/CLI contracts, not shared mutable Python state.

## Hermes calls
1. scos_media_pipeline.py analyze
2. scos_media_pipeline.py plan
3. scos_media_pipeline.py render
4. scos_media_pipeline.py verify
5. CapCut adapter create/lint

## Failure behavior
- Analyzer failure = BLOCKED.
- UNKNOWN subtitle evidence = do not fabricate.
- Temporal QA FAIL = remediation path.
- CapCut failure = preserve canonical artifact and report adapter failure.
- Changed source SHA-256 = invalidate old analysis/plan/evidence.

## Quality lanes
FAST: NVENC P1.
BALANCED: NVENC P3/HQ on the current RTX 5050-class machine.
QUALITY: NVENC P4/HQ or libx264 medium when visual fidelity is prioritized.
INTERPOLATION: explicit candidate only; must pass temporal/visual QA.

## Reuse
SCOS render cache, hardware routing, video-use hard rules, artifact verification,
and production-loop closure remain authoritative. No second competing truth store.
