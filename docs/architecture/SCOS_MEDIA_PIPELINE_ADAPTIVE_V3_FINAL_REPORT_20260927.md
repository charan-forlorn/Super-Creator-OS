# SCOS Adaptive SMOOTH+ V3 R2 Final Report ? 2026-09-27

## Objective
V3 adds a bounded temporal-quality canary between deterministic V2 routing and full-window RIFE. The canary runs on a safe interior micro-span, measures inserted-frame temporal behavior directly, and rejects windows that are temporal outliers before full interpolation.

## Verified source
- Source FPS: 30
- Keep range: 18.263437?50.245583s
- Hard scene cut: 31.166667s
- RIFE: portable `rife-ncnn-vulkan`, `rife-v4.6`, NVIDIA GPU
- Automatic promotion: OFF

## V3 routing
V2 proposed 3 SMOOTH+ spans. V3 executed 3 temporal canaries. The 32.166667?37.166667s span was rejected; 38.166667?39.166667s and 43.166667?44.166667s were accepted. Accepted RIFE duration = 2.0s / 31.982146s (6.25%).

## Benchmark
| Mode | FPS | Render time | SSIM | VMAF | Artifact-spike proxy | Temporal-continuity proxy |
|---|---:|---:|---:|---:|---:|---:|
| PRESERVE | 30.0 | 3.184s | 0.997488 | 97.236146 | 0.156576 | 0.387384 |
| FULL SMOOTH+ | 60.0 | 202.702s | 0.995184 | 95.518445 | 0.316806 | 0.547009 |
| ADAPTIVE V3 | 60.0 | 23.111s | 0.997516 | 97.230870 | 0.453076 | 0.348872 |

V3 reduced RIFE workload by **93.75%** versus FULL and reduced measured render time by **8.77?**. Spatial fidelity remained essentially at the PRESERVE baseline (SSIM delta +0.000028).

## Temporal gate result
Temporal QA: **PASS**. CFR60, monotonic PTS, A/V duration tolerance, and adaptive route integrity passed. The inserted-frame canary is the V3-specific gate; 2/3 candidate windows survived cross-window calibration.

## CapCut
CapCut 9.6.0 draft was created from V3 R2 + canonical `Final_Captions.srt`. One derived-only caption timing repair changed 400ms to 445ms. Final lint: **0 errors / 0 warnings**. Canonical SRT was not modified.

## Promotion state
Automatic promotion remains **disabled / REVIEW**. This is deliberate: the V3 candidate is materially more conservative and much faster than V2, but the current artifact-spike and temporal-continuity proxy values are not yet sufficient for autonomous promotion.

## Evidence
- `evidence/media-pipeline-adaptive-v3/ADAPTIVE_SMOOTHPLUS_V3_R2_RENDER.json`
- `evidence/media-pipeline-adaptive-v3/TEMPORAL_QA_V3_R2.json`
- `evidence/media-pipeline-adaptive-v3/SMOOTHPLUS_V3_BENCHMARK_R2.json`
- `evidence/media-pipeline-adaptive-v3/CAPCUT_V3_VERIFICATION.json`
- `evidence/media-pipeline-adaptive-v3/FINAL_GATE_MATRIX_V3_R2.json`
- `evidence/media-pipeline-adaptive-v3/ADAPTIVE_SMOOTHPLUS_V3_R2_RECEIPT.json`
