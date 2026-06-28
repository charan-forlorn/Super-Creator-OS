# Module 2 — Real FFmpeg Renderer · Phase 5: Testing Report

## Environment
- ffmpeg/ffprobe 8.1.1 (gyan.dev), CPython 3.11.15, Windows 11.
- Fixtures generated at runtime via ffmpeg lavfi (no shipped media).

## New suite — `python scos/render/tests/test_renderer.py`
**Result: 18 passed, 0 failed.**

| Group | Coverage | Checks |
|---|---|---|
| [1] request mapping | D1 `edit_timeline` → `RenderRequest`; duration = end−start; None-audio preserved; run_id→output; result dict | 5 |
| [2] write_edl | D2 EDL shape: sources, `[0,dur]` ranges, summed total, grade/overlays | 4 |
| [3] honest-failure (unit) | missing visual → `RenderError`; empty clips → `RenderError` | 2 |
| [4] integration render | synthetic stills (landscape + square) + voiceover + silent track → real mp4; **1080×1920**; duration ≈ 3.5s; **deterministic** geometry + duration across two runs | 6 |
| [5] integration failure | missing visual → `RenderError`, no output | 1 |

### What the integration test proves
- The full path runs for real: bridge → `vu.py render` (engine) → ffprobe validation.
- Both audio branches exercised (real voiceover + synthesized silent track).
- Output is exactly the target canvas; duration matches the sum of scene durations within tolerance.
- Two independent runs produce identical geometry and duration within 0.05s (determinism).

## Determinism
Geometry identical; duration delta < 0.05s across runs. Byte-exact equality is not asserted (x264/container timestamps vary); geometry + duration stability is the determinism contract.

## Failure-path / edge cases
- Missing/empty visual, empty clip list → `RenderError` (unit + integration).
- Silent scene (no audio) → renders via `anullsrc`.
- Orchestrator end-to-end with stub (nonexistent) assets → `status=failed`, `video_path=None`, trace stops at `render` (verified manually).

## Regression (existing suites)
- `integrations/learning/tests/run_suite.py` → **58 passed**.
- `integrations/shortgen/tests/test_short_generator.py` → **7 passed**.
- `integrations/highlight/tests/test_highlight_engine.py` → **15 passed**.
No regressions; changes isolated to `scos/render` + a CI step.

## CI
`.github/workflows/ci.yml` runs the renderer test on ubuntu (ffmpeg installed). Real render executes in CI — no skip.

## Known caveat
`scos/` is currently untracked in git (pre-existing repo state). The CI step exercises the renderer only once `scos/` is committed; flagged in `production_review.md` as a repo-state action item outside Module-2 code scope.
