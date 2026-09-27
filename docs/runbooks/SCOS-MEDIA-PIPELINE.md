# SCOS Media Pipeline Runbook

## Standard
1. Analyze:
python scripts/scos_media_pipeline.py analyze <source> --srt <optional.srt>

2. Plan:
python scripts/scos_media_pipeline.py plan <evidence.json> --speed balanced --smoothness adaptive

3. Render:
python scripts/scos_media_pipeline.py render <source> <plan.json> <output.mp4>

4. Verify:
python scripts/scos_media_pipeline.py verify <output.mp4> --source <source>

5. CapCut:
Use scos.control_center.capcut_adapter to create/lint the editable draft.

## Profiles
FAST: nvenc_p1_fast
BALANCED: nvenc_p3_hq
QUALITY: nvenc_p4_hq or libx264_quality

## Smoothness policy
Preserve source FPS by default.
If cadence evidence flags a high duplicate ratio and the user explicitly wants
smoother motion, generate a 60fps candidate only. Run temporal QA and visual
inspection before promotion.

## Subtitle policy
Verified SRT or word-level ASR first. OCR fallback. UNKNOWN means stop caption
fabrication; never infer missing text.

## Adaptive SMOOTH+ V2

Build fresh evidence and plan:
```powershell
python scripts/scos_media_pipeline.py analyze <source> --srt <verified.srt> --no-cache --out evidence/media-pipeline-adaptive-v2/MEDIA_EVIDENCE_V2.json
python scripts/scos_media_pipeline.py plan evidence/media-pipeline-adaptive-v2/MEDIA_EVIDENCE_V2.json --smoothness adaptive --speed balanced --out evidence/media-pipeline-adaptive-v2/EDIT_PLAN_ADAPTIVE_V2.json
```

Candidate render:
```powershell
python scripts/scos_media_pipeline.py adaptive-smooth-plus <source> evidence/media-pipeline-adaptive-v2/EDIT_PLAN_ADAPTIVE_V2.json evidence/media-pipeline-adaptive-v2/MEDIA_EVIDENCE_V2.json <output60.mp4> --threshold 0.35 --threads 2:4:4
```

The command is fail-closed for invalid/non-CFR source cadence and never interpolates across hard scene boundaries. Only windows routed `SMOOTH+` are sent to RIFE. `PRESERVE` and `REVIEW` windows remain non-interpolated and are composed into the final CFR60 timeline. Audio is assembled from the exact source segments in the final timeline.

Verification must include `verify --target-fps 60`, route integrity, normalized duplicate drift, fidelity benchmark, visual spot-check, and CapCut lint. Automatic promotion remains disabled.

Benchmark:
```powershell
python scripts/benchmark_smooth_plus.py --source <source> --preserve <p3.mp4> --full <full_smoothplus.mp4> --adaptive <adaptive_v2.mp4> --adaptive-run-json <adaptive_render.json> --preserve-time <seconds> --full-time <seconds> --source-start <keep-start> --keep-duration <keep-duration> --out <benchmark.json>
```


## Adaptive SMOOTH+ V2 R3 Operational State — 2026-09-27

The supported deterministic command remains:
python scripts/scos_media_pipeline.py adaptive-smooth-plus <source> evidence/media-pipeline-adaptive-v2/EDIT_PLAN_ADAPTIVE_V2.json evidence/media-pipeline-adaptive-v2/MEDIA_EVIDENCE_V2.json <output60.mp4> --threshold 0.35 --threads 2:4:4

Operational invariants:
- Probe source FPS on every render; never trust a hard-coded 30fps assumption.
- RIFE target cadence is 60fps.
- A selected window must be scene-safe and evidence-supported.
- REVIEW windows are not interpolated.
- RIFE failure falls back to PRESERVE for that span.
- If no RIFE span successfully renders, the final composition preserves the probed source cadence.
- Final mixed output with any successful SMOOTH+ span is CFR60.
- Audio follows the final edited timeline through segment-aware source trim/concat.
- Temporal QA must pass before candidate promotion.
- CapCut is derived/editable state only.
- Jev/TypeSafe is optional advisory context and cannot override deterministic gates.
- Automatic promotion remains disabled.

R3 final evidence is under evidence/media-pipeline-adaptive-v2/. The current final candidate is SCOS_SMOOTHPLUS_ADAPTIVE_V2_CANDIDATE_R3.mp4.

## Adaptive SMOOTH+ V3 ? Quality-Calibrated Temporal Gate

V3 is the next candidate lane above Adaptive SMOOTH+ V2. It keeps the deterministic V2 route, then executes a small RIFE canary inside each selected window and measures inserted-frame temporal behavior before spending the full-window RIFE cost.

Implementation entry point:
```powershell
python -c "from scos.render.smooth_plus import render_adaptive_smooth_plus_v3; print(render_adaptive_smooth_plus_v3)"
```

Operational invariants:
- Canary duration is bounded to 0.3?0.5s and selected away from scene boundaries.
- Canary metrics include path excess, temporal asymmetry, blend deviation, and jerk.
- Final gate calibration is cross-window and robust (median/MAD), not a hard-coded global VMAF/SSIM threshold.
- Rejected canaries never proceed to full RIFE.
- Successful V3 interpolation produces CFR60; no successful interpolation preserves source cadence.
- Audio remains source-segment trim/concat over the exact final timeline.
- CapCut is derived state only; caption repair must never modify canonical SRT.
- Automatic promotion remains disabled.

V3 R2 evidence:
```text
evidence/media-pipeline-adaptive-v3/
  ADAPTIVE_SMOOTHPLUS_V3_R2_RENDER.json
  TEMPORAL_QA_V3_R2.json
  SMOOTHPLUS_V3_BENCHMARK_R2.json
  CAPCUT_V3_VERIFICATION.json
  FINAL_GATE_MATRIX_V3_R2.json
  ADAPTIVE_SMOOTHPLUS_V3_R2_RECEIPT.json
```

V3 R2 accepted two of three V2 spans, passed Temporal QA, and produced a 60fps candidate with 0 CapCut lint errors/warnings. Promotion remains REVIEW.
