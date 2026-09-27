---
name: scos-media-pipeline
description: Run the SCOS deterministic media intelligence pipeline from source inspection through render, optional RIFE SMOOTH+ candidate, temporal QA, CapCut draft, lint, and evidence closure.
---

# SCOS Media Pipeline

## Mission
Use deterministic workers for repeatable media operations and Hermes for orchestration.
Never fabricate subtitle text, confidence, QA, or external API availability.

## Standard workflow
1. Verify source exists and fingerprint current bytes.
2. Analyze source with scripts/scos_media_pipeline.py analyze.
3. Read evidence and build EditPlan.
4. Use BALANCED NVENC P3/HQ as the current default source-cadence lane.
5. Verify temporal output.
6. Create/lint CapCut draft.
7. Persist artifact/evidence packet.

## SMOOTH+ workflow
SMOOTH+ is candidate-only:
1. Require duplicate/cadence evidence above deterministic threshold.
2. Split interpolation ranges at scene boundaries.
3. Run RIFE v4.6 through the portable Vulkan binary.
4. Keep 60fps candidate CFR and source audio.
5. Run normalized temporal QA at the source FPS.
6. Compare visual fidelity / SSIM against the non-interpolated baseline.
7. Only then consider promotion.

Current full-footage benchmark passed temporal QA and CapCut lint, but SMOOTH+ is
not the default because it is an offline quality lane (~6.3x realtime on the
tested 32s footage).

## TypeSafe / Jev Decision Advisor
Optional only. It receives structured evidence, not raw media.
Use it to advise preserve / smooth_plus / quality routing.
Promotion requires:
- deterministic gate PASS
- Jev Choice=smooth_plus
- confidence >= 0.85
- Temporal QA PASS
- fidelity threshold PASS
No TYPESAFE_API_KEY means UNAVAILABLE; do not fabricate or silently assume a Jev result.

## Subtitle policy
Verified SRT or word-level ASR first. OCR fallback.
UNKNOWN means stop caption fabrication.

## Hard boundaries
Hermes never becomes the media codec/renderer.
CapCut never becomes canonical project state.
Jev never becomes execution authority.
No publish/dispatch/destructive action is part of this skill.

## Handoff packet
source_path
source_sha256
media_evidence_path
edit_plan_path
render_profile
smoothplus_candidate_path
temporal_qa_path
capcut_project_path
capcut_lint_result
artifact_sha256
decision_advisor_result

## Adaptive SMOOTH+ V2

Use `scripts/scos_media_pipeline.py adaptive-smooth-plus` for deterministic windowed interpolation candidates.

Required handoff fields:
- source_sha256
- source_fps / CFR state
- scene boundaries
- micro-window evidence
- PRESERVE / SMOOTH+ / REVIEW decisions
- selected smooth spans
- RIFE model/GPU/threads
- output CFR/FPS/PTS checks
- segment-aware audio mapping result
- normalized duplicate drift
- SSIM/VMAF/artifact benchmark
- CapCut draft/lint
- promotion decision

Never treat Jev as execution authority. Missing TypeSafe key means `UNAVAILABLE`. REVIEW remains REVIEW. Automatic promotion is off.

## V2 Policy Override — Jev Is Optional

For Adaptive SMOOTH+ V2, Jev/TypeSafe is **optional advisory context only**. Deterministic routing and deterministic safety gates do not require a Jev result. A missing `TYPESAFE_API_KEY` means `JEV UNAVAILABLE`; the system must preserve deterministic execution and may route ambiguous windows to `REVIEW`. Jev may be prepared for ambiguous-case evaluation after deterministic benchmark policy calibration, but it can never override deterministic safety gates or become execution authority. Automatic promotion remains disabled in this phase regardless of Jev availability.


## R3 Deterministic Invariants

- Always probe current source FPS; caller FPS is advisory only and must match the probe.
- RIFE uses an explicit 60fps target; do not assume 2x source FPS.
- If no RIFE span is successfully rendered, preserve source cadence.
- Mixed successful SMOOTH+ output is CFR60.
- Route QA must reject overlapping or scene-crossing smooth spans.
- Audio mapping is segment-aware trim/concat over the final edited timeline.
- Automatic promotion is disabled; REVIEW is never silently upgraded.
- The final evidence packet for R3 is evidence/media-pipeline-adaptive-v2/ADAPTIVE_SMOOTHPLUS_V2_RUN_RECEIPT_R3.json.

## Adaptive SMOOTH+ V3

V3 is the preferred experimental gate above V2 when interpolation quality must be checked before full-window RIFE.

1. Run deterministic V2 micro-window analysis.
2. For each V2-selected span, choose an interior 0.3?0.5s canary.
3. Render only the canary with RIFE v4.6 at 60fps.
4. Measure inserted-frame triplet metrics: path excess, asymmetry, blend deviation, jerk.
5. Calibrate across observed canaries with robust median/MAD statistics.
6. Reject temporal outliers before any full-window RIFE call.
7. Render full RIFE only for accepted spans, then compose CFR60 with segment-aware audio.
8. Run Temporal QA, source-FPS fidelity benchmark, and CapCut lint.

V3 safety:
- Never cross a hard scene boundary.
- Fewer than two canaries = REVIEW; no autonomous promotion.
- RIFE/model failure = PRESERVE fallback.
- Automatic promotion is OFF.
- CapCut remains derived editable state; canonical SRT/evidence remain authoritative.

## Adaptive SMOOTH+ V4 — Multi-Class Calibration Corpus

V4 is an offline calibration layer above V3, not a replacement for deterministic V3 safety.

Workflow:
1. Collect verified V3/RIFE canary evidence from multiple footage classes.
2. Build `V4_CORPUS_MANIFEST.json` with source paths and SHA-256 values.
3. Build `V4_CALIBRATION_PROFILE.json` using robust median/MAD distributions for path excess, blend deviation, asymmetry, and jerk.
4. Validate in-domain and negative holdouts with `python -m scripts.calibrate_smoothplus_v4`.
5. Keep automatic promotion OFF until the corpus contains independent source files across each class and additional motion families.

V4 safety:
- unknown calibration class = fail closed;
- V4 cannot override V3 scene safety, source/CFR checks, RIFE availability, audio invariants, or REVIEW;
- calibration disagreement resolves to REVIEW/PRESERVE;
- the current V4 profile is not production authority.


## Adaptive SMOOTH+ V4.1 - Multi-Class Calibration Corpus

LOSO is source-level. Calibration precedence: class profile -> source-excluded global calibrated fallback -> REVIEW. V4.1 is offline/review-only and cannot override V3 safety gates.

## Adaptive SMOOTH+ V4.1 — source-level calibration

V4.1 is finalized as an offline calibration/review layer.

Corpus requirements now enforced:
- >=3 independent source files per class;
- >=2 newly introduced source files per class versus V4 baseline;
- >=1 distinct motion family beyond screen/UI;
- SHA-256 source identity;
- leave-one-source-out validation.

Current evidence:
- 10 unique sources;
- 20 canary observations;
- classes: screen_recording_real (3), portrait_screen_real (4), natural_motion_real (3);
- z_review=6.0 selected after deterministic threshold sweep;
- 10 LOSO folds;
- positive retention 100%;
- negative rejection 100%;
- false accepts 0;
- false rejects 0;
- source-level leakage false.

The V4.1 calibration threshold may inform offline review analysis only. It cannot override V3 deterministic safety, scene-cut safety, source integrity, Temporal QA, RIFE availability, or Human review. Automatic promotion remains disabled.
