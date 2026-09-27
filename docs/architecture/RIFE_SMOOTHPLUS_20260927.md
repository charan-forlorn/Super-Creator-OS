# RIFE SMOOTH+ — 2026-09-27

## Engine
rife-ncnn-vulkan 20221029 Windows portable release.
Model: rife-v4.6.
License: MIT.
GPU: NVIDIA GeForce RTX 5050 Laptop GPU via Vulkan device 0.
No CUDA/PyTorch runtime dependency is required by the portable build. citeturn171173search0

## Full-footage benchmark
Real source window:
18.263437–50.245583 s
30fps CFR
duplicate-frame estimate: 47.52%

SMOOTH+:
30 → 60fps
scene cut split at 31.166667s
RIFE v4.6
threads 2:4:4
RTX 5050 Vulkan
Full candidate build elapsed ≈ 203 s
Output video ≈31.967 s
Audio ≈31.982 s
Video frames: 1918

## QA
Temporal QA:
PASS
60fps CFR
PTS monotonic
A/V delta ≈15 ms
duplicate cadence drift after normalization to 30fps ≈3.06 percentage points

Downsampled 60fps candidate → 30fps vs source:
SSIM All ≈0.995146

The candidate visibly preserves scene composition and subtitles in sampled
contact sheets. No sampled hard-cut corruption was observed.

## Important performance trade-off
SMOOTH+ is an offline quality lane, not an interactive FAST lane.
The current full-footage test took ≈203 s for ≈32 s of footage (~6.3x realtime).

## Automation status
SMOOTH+ is candidate-only.
It is NOT enabled as the default render lane.
Promotion requires deterministic gates, temporal QA, and optional TypeSafe/Jev
decision advice; unresolved uncertainty remains REVIEW.

## Optimization finding
RIFE thread setting 2:4:4 reduced a 4-second benchmark from about 14.06 s
(RIFE inference alone at 2:2:2) to about 9.27 s while still producing 240 frames.
The official RIFE documentation recommends tuning load/proc/save worker counts
for GPU utilization and memory. citeturn171173search0

## Adaptive SMOOTH+ V2

The V2 lane is windowed rather than full-clip RIFE. The source FPS is probed dynamically and must be CFR before interpolation. Kept ranges are first split at detected hard scene boundaries. Each scene-safe segment is analyzed in deterministic micro-windows (default 1.0s, bounded to 0.5–2.0s).

Window evidence includes duplicate/cadence ratio, motion energy, temporal inconsistency, scene-cut proximity and interpolation-risk score. Routing is fail-closed:
- `PRESERVE` — keep source cadence/content and resample to final CFR60 only at composition time when SMOOTH+ is selected elsewhere.
- `SMOOTH+` — run RIFE v4.6 only for that window.
- `REVIEW` — do not interpolate; retain the source window and optionally surface it to a future decision advisor.

RIFE no longer assumes 30fps. A source-FPS probe determines extraction and output cadence; 2x interpolation produces `source_fps * 2`. The official portable `rife-ncnn-vulkan` v4.6 build and `2:4:4` worker setting remain unchanged.

The composer uses source `atrim`/`asetpts` per timeline part and concatenates those audio segments. It therefore does not use the invalid `source_start + total_duration` shortcut when keep ranges are disjoint.

Current real-footage V2 result: 7.0s of 31.982146s selected for RIFE; three spans (32.166667–37.166667, 38.166667–39.166667, 43.166667–44.166667) with no scene-cut crossing. Render time 58.95s; Temporal QA PASS; SSIM 0.996930; VMAF 96.912490.

Promotion remains candidate-only.


## Adaptive V2 R3 Engineering Closure — 2026-09-27

The RIFE lane now uses two distinct FPS facts:
- source FPS: always derived from deterministic probe_source() and used for extraction/validation;
- target FPS: explicit 60fps contract for SMOOTH+ output.

This removes the previous implicit source_fps * 2 assumption, which only generalized cleanly for 30fps input. On non-30fps sources, RIFE now requests the frame count required to reach the explicit target cadence.

Fallback behavior is fail-closed: unavailable RIFE or per-window RIFE failure does not fabricate CFR60 output. Successful SMOOTH+ spans produce CFR60 mixed output; all-preserve fallback keeps the probed source cadence.