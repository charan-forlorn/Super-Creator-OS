# SCOS + Hermes Media Intelligence Implementation Blueprint

## Goal
Upgrade Super Creator OS into a deterministic, evidence-driven media editing
system that can be orchestrated by Hermes, finished in CapCut, and verified by
SCOS without making Hermes or CapCut runtime dependencies.

## Canonical flow
Reconcile → Source Verification → Silence Detection → Scene/Ad Verification
→ Cadence Analysis → Subtitle Evidence → EditPlan → Deterministic Render
→ Temporal QA → CapCut Draft/Lint → Final Artifact Verification → Production
Loop/Evidence Seal → Learning.

## Runtime components
- scos/media_analysis/: source, silence, scene, ad boundary, cadence, subtitle evidence, plans, analysis cache.
- scos/render/source_edit.py: source-media cut/render lane.
- scos/render/hardware.py: encoder discovery/runtime probe.
- scos/render/render_cache.py: content-addressed render reuse.
- scos/control_center/capcut_adapter.py: CapCut boundary.
- existing production-loop/evidence authorities remain canonical for closure.

## Operator components
- .agents/skills/scos-media-pipeline/SKILL.md
- scripts/scos_media_pipeline.py
- Control Center commands may call explicit contracts but must not import Hermes.

## Quality policy
Default source-edit BALANCED = NVENC P3/HQ, because the real machine benchmark
showed it retains source cadence while staying above the 2x acceleration target
relative to the CPU baseline. P4/HQ remains available as a quality-focused
profile. FAST = P1. QUALITY = libx264 or slower NVENC.
Adaptive smoothness = candidate 60fps review, not automatic promotion.

## Evidence
Every run should retain:
- source media contract
- source SHA-256 / analysis cache key
- silence spans
- scene boundary evidence
- advert boundary evidence
- cadence stats
- subtitle evidence source
- EditPlan
- render profile/encoder signature
- temporal QA result
- CapCut draft/lint result
- artifact SHA-256
- production-loop/evidence receipt

## Hermes role
Hermes is the Primary Operator/Orchestrator.
Hermes chooses, sequences, and interprets structured results. Deterministic
workers perform media operations.

## CapCut role
CapCut is an editable finishing surface. Canonical state is outside CapCut.
CapCut adapter failures must not corrupt canonical EDL/SRT/evidence state.

## JAF decision
Do not add Juspay JAF as a dependency. Reuse its useful architectural ideas
(immutable run state, typed tool contracts, effects at the edge) in SCOS-native
Python contracts and JSON evidence.


## SMOOTH+ / TypeSafe extension — 2026-09-27

SMOOTH+ is a candidate-only RIFE v4.6 Vulkan 30→60fps lane. It is never selected solely from model judgment. Deterministic cadence/scene evidence, RIFE availability, Temporal QA and visual/fidelity thresholds must pass first.

TypeSafe AI / Jev is an optional Decision Advisor. It receives structured media evidence, not raw video, and returns typed judgments. Confidence must meet the configured floor before a judgment can influence promotion. No API key means UNAVAILABLE and deterministic rules continue without pretending Jev was consulted.

Current full-footage RIFE candidate passed normalized temporal QA and CapCut lint, but SMOOTH+ remains opt-in pending broader footage-family regression. The current verified default remains NVENC P3/HQ source-cadence preservation.

## Adaptive SMOOTH+ V2 — 2026-09-27

Adaptive SMOOTH+ V2 is now a deterministic candidate capability layered on the canonical source-edit pipeline.

Flow:
Source Verification → Scene segmentation → 0.5–2.0s micro-window temporal analysis → deterministic PRESERVE/SMOOTH+/REVIEW routing → selective RIFE v4.6 → mixed CFR60 composition → segment-aware audio composition → Temporal QA → fidelity/temporal benchmark → CapCut lint → candidate promotion decision.

Implementation:
- `scos/media_analysis/adaptive_smooth_plus_v2.py` — window evidence and routing.
- `scos/render/rife_interpolator.py` — dynamic source-FPS RIFE execution.
- `scos/render/smooth_plus.py` — selective RIFE + preserve timeline composition and exact per-segment audio trimming.
- `scos/media_analysis/temporal_quality.py` — CFR60, route integrity, scene-cut safety and normalized cadence verification.
- `scripts/scos_media_pipeline.py adaptive-smooth-plus` — deterministic pipeline entry point.
- `scripts/benchmark_smooth_plus.py` — canonical benchmark harness (kept-source reference timeline).

Safety policy:
- non-CFR or invalid-FPS source → fail closed for adaptive interpolation.
- RIFE unavailable → PRESERVE fallback.
- hard scene boundary or high interpolation risk → PRESERVE/REVIEW; never cross the cut.
- REVIEW windows remain non-interpolated and are future candidates for optional Jev advice only.
- automatic promotion remains OFF.
- CapCut remains a derived editable surface; its caption timing repair is never written back to canonical SRT.

Verified benchmark for the current 30fps source:
- selected RIFE duration: 7.0s / 31.982146s keep timeline (21.89%).
- RIFE workload reduction: 78.11% versus full SMOOTH+.
- adaptive render time: 58.95s versus 202.70s full SMOOTH+ (3.44x speedup).
- adaptive SSIM against kept source: 0.996930; VMAF: 96.912490.
- full SMOOTH+ SSIM: 0.995184; VMAF: 95.518445.
- normalized duplicate drift: 0.03316; Temporal QA PASS.
- CapCut final lint: 0 errors / 0 warnings after derived caption-duration normalization from 400ms to 445ms; canonical SRT remains unchanged.

Automatic promotion remains disabled pending broader footage-family calibration.


## Adaptive SMOOTH+ V2 R3 Finalization — 2026-09-27

The Adaptive SMOOTH+ V2 capability is implemented and re-verified against current source bytes.

R3 hardening:
- Source FPS is always authoritative from probe_source(); caller-supplied input_fps is accepted only when it matches the probe.
- RIFE has an explicit target_fps=60.0 contract and requests the correct output frame count for the target cadence instead of assuming 2x source FPS.
- If RIFE is unavailable or every selected RIFE span falls back, composition preserves the probed source cadence rather than forcing CFR60 without interpolation.
- Adaptive route QA checks sorted/non-overlapping selected spans and selected duration against the kept timeline.
- Hard scene boundaries remain fail-closed.

Final R3 candidate:
C:\Users\chara\Downloads\video_edit_test\SCOS_SMOOTHPLUS_ADAPTIVE_V2_CANDIDATE_R3.mp4

Final benchmark:
- Adaptive RIFE workload reduction: 78.1128%
- Full SMOOTH+ render: 202.7016s
- Adaptive render: 59.0098s
- Full to Adaptive speedup: 3.4351x
- Adaptive SSIM: 0.996930
- Full SMOOTH+ SSIM: 0.995184
- Preserve SSIM: 0.997488
- Adaptive VMAF: 96.91249
- Adaptive normalized duplicate drift: 0.033160
- Adaptive artifact-spike proxy: 0.445255
- Adaptive temporal-motion-continuity proxy: 0.420722

Temporal QA: PASS. Output is CFR60, 1920 frames, PTS monotonic, A/V duration delta 18ms, and route integrity PASS.

CapCut R3: draft created from the final candidate and canonical SRT; derived-only caption timing repair applied; final lint 0 errors / 0 warnings.

Automatic promotion remains disabled. The adaptive lane remains REVIEW because the benchmark shows a material efficiency gain but also a higher artifact-spike proxy and lower temporal-motion-continuity proxy than FULL SMOOTH+.

## Adaptive SMOOTH+ V3 ? Quality-Calibrated Temporal Gate ? 2026-09-27

V3 extends the verified V2 route with a bounded temporal canary before full-window RIFE. The design is intentionally local, deterministic, reversible, and does not add a second heavy model, a new agent runtime, or a Jev dependency.

Flow:
Source verification ? V2 micro-window route ? 0.3?0.5s interior RIFE canary ? inserted-frame temporal triplets ? cross-window robust calibration ? PRESERVE / SMOOTH+ / REVIEW ? full-window RIFE only for accepted spans ? CFR60 composition ? segment-aware audio ? Temporal QA ? source-FPS fidelity benchmark ? CapCut lint ? promotion review.

V3 R2 verified on the current 30fps source:
- V2 proposed 3 spans; 3 canaries executed; 2 accepted and 1 rejected.
- Accepted spans: 38.166667?39.166667s and 43.166667?44.166667s.
- Accepted interpolation duration: 2.0s / 31.982146s (6.25%).
- RIFE workload reduction: 93.7465% versus FULL SMOOTH+.
- Measured render time: 23.1112s versus 202.7016s FULL (8.7707x faster).
- SSIM: 0.997516; VMAF: 97.230870; subtitle ROI SSIM: 0.997415.
- Temporal QA: PASS; CapCut 9.6.0 lint: 0 errors / 0 warnings.
- Automatic promotion: OFF / REVIEW.

V3-specific safety rules:
- Canary must remain inside a single scene-safe window and never cross a detected hard cut.
- Source-relative temporal statistics are evidence only; final canary gating uses cross-window robust calibration so duplicate-heavy screen recordings do not create false rejection from a mismatched baseline.
- Fewer than two canaries cannot establish cross-window calibration and therefore remain REVIEW.
- Any failed canary prevents the corresponding full-window RIFE run.
- If all canaries reject or RIFE is unavailable, composition preserves source cadence.
- Automatic promotion remains disabled until multiple footage families show stable temporal and spatial quality.

V3 evidence is under `evidence/media-pipeline-adaptive-v3/`; the current candidate is `SCOS_SMOOTHPLUS_ADAPTIVE_V3_CANDIDATE_R2.mp4`.

## Adaptive SMOOTH+ V4 — Multi-Class Calibration Corpus — 2026-09-27

V4 adds an offline class-conditioned temporal calibration layer above the V3 canary. V3 remains the active experimental gate; V4 does not grant execution authority or enable automatic promotion.

Implementation:
- `scos/media_analysis/adaptive_smooth_plus_v4.py` — robust median/MAD class calibration and scoring.
- `scos/media_analysis/tests/test_adaptive_smooth_plus_v4.py` — unit/fail-closed coverage.
- `scripts/calibrate_smoothplus_v4.py` — reproducible corpus/hash/holdout validator.
- `evidence/media-pipeline-adaptive-v4/V4_CORPUS_MANIFEST.json`
- `evidence/media-pipeline-adaptive-v4/V4_CALIBRATION_PROFILE.json`
- `evidence/media-pipeline-adaptive-v4/V4_VALIDATION_REPORT.json`

Verified V4 corpus:
- 3 real screen-oriented classes.
- 6 accepted canary observations, 2 per class.
- Source SHA-256 verification PASS for all samples.
- Four in-domain holdouts scored SMOOTH+.
- Two negative/outlier holdouts scored REVIEW.
- Unknown class fails closed.
- V4 tests: 6 passed.
- Full SCOS regression after V4: 2863 passed, 21 skipped, 21 deselected.

V4 limitations:
- only one unique source file per class;
- local corpus is screen-oriented;
- no talking-head source is currently available.

Policy:
- V4 remains calibration/research only.
- Any disagreement with V3 deterministic safety resolves to REVIEW/PRESERVE.
- Automatic promotion remains disabled.
- Expand corpus with independent source files and additional motion families before using V4 calibration for autonomous routing.


## Adaptive SMOOTH+ V4.1 - Multi-Class Calibration Corpus - 2026-09-27

9 sources / 3 classes / 18 canaries / LOSO 100% positive retention / 100% negative rejection / 0 false accepts / 0 source leakage. Automatic promotion remains disabled.

## Adaptive SMOOTH+ V4.1 — 2026-09-28 FINALIZED

V4.1 source-level generalization is complete.

Verified corpus:
- screen_recording_real: 3 sources, 2 new vs V4
- portrait_screen_real: 4 sources, 2 new vs V4
- natural_motion_real: 3 sources, 3 new vs V4
- total: 10 unique sources / 20 canary observations
- source identity: SHA-256
- different motion family: natural_motion_real

LOSO:
- 10 held-out source folds
- 20 observations
- z_review=6.0
- positive retention=100%
- negative rejection=100%
- false accepts=0
- false rejects=0
- source-level leakage=false
- overall=PASS

Threshold selection:
A deterministic sweep of z_review 4.0 through 10.0 found a stable plateau from 5.5 upward with 100% positive retention, 100% negative rejection, and zero false accepts. V4.1 records 6.0 as the operational offline calibration threshold.

Safety:
- V3 deterministic safety remains authoritative.
- V4.1 is offline/review-only.
- Automatic promotion remains disabled.
- Jev/TypeSafe is not execution authority.
- V4.1 cannot override scene-boundary, temporal QA, RIFE availability, source integrity, or other deterministic safety gates.

Regression:
- V4.1 focused tests: 11 passed.
- Full SCOS regression: 2868 passed, 21 skipped, 21 deselected.
- compileall: PASS.
