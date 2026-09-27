# SCOS Media Pipeline Final Report — 2026-09-27

## Delivery status
Implemented the deterministic media-intelligence pipeline, Hermes project skill,
CapCut adapter, temporal QA, content-addressed analysis cache, source-FPS
preservation fix for the existing video-use helper, source-edit render profiles,
and persistent implementation blueprint.

No Hermes/Codex/OpenCode/Ollama runtime dependency was added to the SCOS product layer.

## Real source
57.7333 s
2560x1528
30 fps CFR
H.264
AAC 48 kHz stereo
1732 frames
Estimated duplicate-frame ratio: 47.52%

## Source-derived edit decision
Leading silence: 0.000000–18.263437 s
Advert/content boundary: 50.245583 s
Late scene transition evidence: 56.066667 s
Final keep range: 18.263437–50.245583 s
Final duration: 32.00 s

## Render lanes
CPU baseline: libx264 medium CRF18 — 7.58855 s
FAST: NVENC P1 — 2.35936 s — 3.22x faster than CPU baseline
BALANCED: NVENC P3/HQ — 3.18425 s — 2.38x faster than CPU baseline
QUALITY candidate: NVENC P4/HQ — 4.00856 s

The new BALANCED profile is P3/HQ because it is comfortably above the requested
2x acceleration target while avoiding the fastest/lowest-quality P1 lane.

## Fidelity / temporal QA
Balanced P3 output:
H.264 yuv420p
2560x1528
30 fps CFR
960 frames
A/V duration delta: 18 ms
PTS monotonic: PASS
Duplicate ratio drift: 3.32 percentage points
SSIM All: 0.998652
Temporal QA: PASS

## Subtitle evidence
The supplied verified SRT contains 7 cues.
The pipeline accepts verified SRT as canonical caption evidence and refuses to
fabricate text when ASR/OCR is uncertain.

## CapCut
CapCut Desktop 9.6.0.
Final editable draft:
C:\Users\chara\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\AI_Edit_SCOS_P3_FINAL

Final CapCut lint:
0 errors
0 warnings

## Hermes
Project skill:
scos-media-pipeline

Project trust:
active

Skill listing:
enabled

Live Hermes one-shot smoke:
blocked by stale/no-running host gateway state; the bounded smoke attempt
produced no model progress. This is an environment integration finding and was
not misreported as PASS.

## JAF
Juspay Agent Framework was evaluated but not added as a runtime dependency.
Selective concepts were adopted natively:
immutable evidence snapshots
typed tool/result contracts
effects isolated at subprocess/tool edges
structured run packets

## Verification
Focused media/control tests: 8 passed
SCOS render regression tests: 15 passed
compileall: PASS
CapCut real adapter create: PASS
CapCut real lint: PASS
Analysis cache: real MISS then HIT
Temporal QA: PASS

## Final artifacts
SCOS_Round_P3_FINAL.mp4
SCOS_Round_Fast_FINAL.mp4
Final_Captions.srt
scos_media_evidence_v4.json
scos_edit_plan_p3.json
FINAL_RUN_RECEIPT.json

See IMPLEMENTATION_BLUEPRINT.md for the canonical handoff architecture.


## SMOOTH+ full-footage result
RIFE v4.6 / Vulkan / RTX 5050 was run on the real 32-second kept footage.
The keep range was split at the verified scene boundary 31.166667s so RIFE never
interpolates across the hard scene cut.

Segment 1:
18.263437–31.166667 s
387 input frames → 774 output frames
elapsed 77.8769 s

Segment 2:
31.166667–50.245583 s
572 input frames → 1144 output frames
elapsed 123.4651 s

Total SMOOTH+ build elapsed: 202.7016 s.
The resulting video is 60fps / H.264 / 2560x1528 with 1918 video frames.
Video duration is 31.966667 s; audio duration is 31.982 s (15.3 ms delta).


Normalized Temporal QA:
PASS
- 60fps CFR
- PTS monotonic
- A/V duration delta <= 100 ms
- duplicate-ratio drift measured after normalizing the 60fps result to the
  source 30fps cadence: 3.06 percentage points

Fidelity:
Downsampled SMOOTH+ 60fps result to 30fps and compared against the original
kept source window:
SSIM All = 0.995146.

The sampled full-video contact sheets preserved composition, on-screen text,
scene boundaries, and framing. No sampled interpolation corruption was found.

Motion evidence:
The 4-second real-footage benchmark showed RIFE v4.6 substantially reduced
near-duplicate transitions compared with naive 30→60 frame duplication.
The 2:4:4 worker configuration reduced RIFE inference time from ~14.06s to
~9.27s on the 4-second benchmark while still producing the full 2x frame count.


## TypeSafe AI / Jev decision advisor
The corrected technology is TypeSafe AI's Jev / System One model, not a generic
JAF runtime. Jev is used only as an optional typed decision advisor.
TypeSafe documents Choice, Score and Noul judgments with probabilities/confidence,
and its workflow evaluation material explicitly recommends decomposing tasks into
deterministic rules plus narrow intelligent judgments. citeturn101998search0turn396513search5

SCOS adapter:
scos/ai/typesafe_jev.py

Current machine:
TYPESAFE_API_KEY is absent.
Therefore live Jev state is UNAVAILABLE and the adapter fails closed.
No external AI decision was fabricated or silently assumed.

Jev will only influence SMOOTH+ promotion when:
deterministic gate = PASS
Choice = smooth_plus
confidence >= 0.85
Temporal QA = PASS
fidelity threshold = PASS

## Final policy
Default = NVENC P3/HQ, preserve source FPS.
SMOOTH+ = explicit candidate lane.
Automatic promotion = OFF.
Optional TypeSafe decision advice = OFF until a valid server-side key is configured
and the decision path has its own regression set.
