# Module 2 — Real FFmpeg Renderer · Phase 4: Implementation Report

## What was built
A SCOS-owned renderer layer that produces real video by driving the vendored video-use engine over its public CLI.

### Files created
- `scos/render/base.py` — `RenderBackend` ABC; `RenderRequest`, `RenderClip`, `RenderProfile`, `RenderResult` dataclasses; `RenderError`.
- `scos/render/edl_bridge.py` — `build_scene_clip` (still + voiceover/silent → exact-duration canvas clip), `write_edl` (D2 EDL), `prepare_render_inputs`, `_validate_clip_inputs`.
- `scos/render/video_use_backend.py` — `VideoUseBackend(RenderBackend)`: bridge → `vu.py render` subprocess → ffprobe validation → `RenderResult`.
- `scos/render/tests/test_renderer.py` — 5 test groups (18 checks).

### Files modified
- `scos/render/ffmpeg_engine.py` — stub replaced; `render(input_data, backend=None)` entrypoint preserved (orchestrator untouched).
- `.github/workflows/ci.yml` — added the Module-2 renderer test step.

## Design decisions honored
- **Stable interface:** SCOS depends on `scos/render` only; **zero** `integrations/video-use` imports (`grep` clean). The single engine touchpoint is `subprocess([... vu.py, "render", edl, "-o", out])`.
- **No engine modification / no logic duplication:** grade, concat, loudnorm, composite all remain in the engine. The only new FFmpeg is the still→clip bridge (an input format the engine lacks).
- **No magic values:** all encode constants live on `RenderProfile`.
- **Structured logging:** `logging` module throughout (not `print`).
- **Typed:** dataclasses + type hints across the module.
- **DI:** `render(input_data, backend=None)` accepts an injected backend (used by unit tests via a fake backend).

## Honest-failure behavior
Missing/empty visual, declared-but-missing audio, non-positive duration, engine non-zero exit, or invalid output each raise `RenderError`. Through the orchestrator this surfaces as `execution_trace[-1] = {stage: render, status: failed, error: …}` with `video_path=None` — verified.

## Notable implementation details
- Silent scenes (no `audio_path`) get a synthesized `anullsrc` stereo track so the engine's audio fades/loudnorm always have a stream.
- Bridge clips letterbox via `scale=…:force_original_aspect_ratio=decrease,pad=…,setsar=1` (handles landscape and square sources → 1080×1920).
- Output validation compares ffprobe geometry against `RenderProfile`; mismatch → `RenderError`.

## Out of scope / untouched
`scos/core/orchestrator.py`, other agents, `integrations/**`, `memory/**`, learning loop, `input/reference/`, `README.md`. No Stage-2 features.
