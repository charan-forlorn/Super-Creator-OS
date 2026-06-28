# Module 2 — Real FFmpeg Renderer · Phase 3: Implementation Plan

## Task breakdown
1. `scos/render/base.py` — interface + dataclasses + `RenderError`.
2. `scos/render/edl_bridge.py` — still+audio → per-scene clip; D2 EDL writer; input validation.
3. `scos/render/video_use_backend.py` — bridge → `vu.py render` subprocess → ffprobe validation → `RenderResult`.
4. `scos/render/ffmpeg_engine.py` — replace stub; keep `render(input_data, backend=None)` entrypoint; map D1 → `RenderRequest`.
5. `scos/render/tests/test_renderer.py` — unit + integration (synthetic lavfi fixtures).
6. `.github/workflows/ci.yml` — add the renderer test step.
7. Lifecycle docs + ADR-001 + STAGE1_STATUS.md.

## Dependencies
- System: `ffmpeg` + `ffprobe` on PATH (already a project prerequisite; installed in CI).
- Python: stdlib only for SCOS render code (`subprocess`, `json`, `logging`, `dataclasses`, `pathlib`). No new pip deps.
- Engine: `integrations/video-use/vu.py` (already present).

## Risk analysis
| Risk | Likelihood | Mitigation |
|---|---|---|
| Engine fails silently | Med | returncode check + ffprobe output validation → `RenderError`. |
| Windows path in filtergraph | Low | bridge uses plain `-i` inputs only. |
| Missing assets (stub upstream) | Expected | honest `RenderError` → `render: failed`. |
| Double-encode cost | Low | intermediate clips at target canvas; modest CRF. |

## Acceptance criteria
- Real `.mp4` from synthetic stills+audio; ffprobe = 1080×1920; duration ≈ Σ scene durations.
- Deterministic geometry + duration across two runs.
- Missing asset → `RenderError`; orchestrator records `render: failed`, `video_path=None`.
- SCOS imports zero `integrations/video-use` symbols.
- New test green locally and in CI (no skip).

## Definition of Done
All acceptance criteria met; existing suites still green; only in-scope files changed; all lifecycle docs written; Stage Gate evaluated.
