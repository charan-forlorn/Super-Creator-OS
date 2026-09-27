# Media Intelligence Pipeline Contract v1

Canonical deterministic media-analysis and source-edit contract.

Stages:
Source Probe → Silence → Scene/Ad Evidence → Cadence → Subtitle Evidence
→ Edit Plan → Render → Temporal QA → CapCut Adapter → Artifact Closure.

Rules:
- Never mutate source bytes.
- Never fabricate text when ASR/OCR is uncertain.
- Preserve source cadence unless interpolation is explicitly requested.
- Runtime-probe encoder availability.
- Verify CFR/FPS, PTS monotonicity, duration and cadence drift after render.
- CapCut is an adapter; canonical state remains outside CapCut.
- Changed source bytes invalidate prior analysis cache entries.
- Human publication and destructive external actions remain outside this capability.

Render profiles:
- nvenc_p1_fast
- nvenc_p3_hq (default BALANCED source-edit lane)
- nvenc_p4_hq
- libx264_quality

## Adaptive SMOOTH+ V2 extension

Adaptive interpolation is an opt-in candidate lane. It requires a verified local CFR source, dynamic FPS probe, known scene boundaries, deterministic micro-window evidence, selective RIFE execution, mixed CFR60 composition, segment-aware audio mapping, and post-render Temporal QA. Deterministic safety gates take precedence over any decision-advisor output.
