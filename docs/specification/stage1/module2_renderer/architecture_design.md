# Module 2 — Real FFmpeg Renderer · Phase 2: Architecture Design

## Goal
Replace the render stub with a production renderer that emits a real, loudness-normalized vertical `.mp4`, while (a) keeping SCOS dependent on a **stable renderer interface** rather than on `integrations/video-use`, and (b) **reusing the vendored engine** without duplicating its FFmpeg logic or modifying it.

## Architecture

```
orchestrator.run_pipeline
   │ edit_timeline (D1: clips[{asset_path,audio_path,start,end}])
   ▼
scos/render/ffmpeg_engine.render(input_data)      ← stable entrypoint (unchanged signature)
   │ maps D1 → RenderRequest; picks default backend (DI-overridable)
   ▼
RenderBackend (ABC, scos/render/base.py)
   └── VideoUseBackend (scos/render/video_use_backend.py)
         1. edl_bridge.prepare_render_inputs: (still,voiceover) → per-scene clip → D2 edl.json
         2. subprocess: vu.py render <edl> -o <out>      (vendored engine, black box)
         3. ffprobe-validate output (geometry, non-empty) → RenderResult
   ▼
{"video_path": …}  → orchestrator → QA → memory
```

## Components & interfaces
- **`base.py`** — `RenderBackend` ABC (`render(request) -> RenderResult`); typed dataclasses `RenderRequest`, `RenderClip`, `RenderProfile` (single source of encode constants), `RenderResult`; `RenderError` (one exception type for all hard failures).
- **`edl_bridge.py`** — the only new FFmpeg: letterbox a still to canvas + attach voiceover (or synthesized silent track) → exact-duration clip; emit a D2 EDL pointing at the clips. Plain `-i` inputs only (no path-in-filtergraph → avoids the Windows drive-colon hazard).
- **`video_use_backend.py`** — orchestrates bridge → engine subprocess → validation. Surfaces the engine's stderr tail on failure (the engine swallows it internally).
- **`ffmpeg_engine.py`** — D1→`RenderRequest` mapping + the stable `render(input_data, backend=None)` function the orchestrator already calls; default backend `VideoUseBackend`, injectable for tests.

## Data flow / contracts
- D1 `clip.end - clip.start` → `RenderClip.duration_s`; `asset_path`→visual, `audio_path`→voiceover (relative paths anchored at repo root).
- D2 EDL: each clip is a `source` with a full `[0, duration]` range; `grade` from `RenderProfile.grade` ("none" default); empty `overlays`; null `subtitles`.
- Output: `scos/work/video/<run_id>.mp4`; intermediates under `scos/work/<run_id>/`.

## Integration points
- **Only** touchpoint to `integrations/video-use` is the `vu.py render` subprocess (process boundary). Zero engine symbols imported.
- Orchestrator unchanged: it still calls `ffmpeg_engine.render({...})`.

## Reused components
- Engine pipeline (grade, per-segment encode, lossless concat, two-pass loudnorm, composite) via `vu.py`.
- D2 EDL schema mirrored from `integrations/adapter/timeline_to_edl.py`.
- Test/CI conventions from `integrations/shortgen/tests/*` and `.github/workflows/ci.yml`.

## Risks & mitigations
- **Double-encode** (clip build → engine re-extract): accepted; clips built at target canvas so the engine pass is light.
- **Silent engine failure:** mitigated by subprocess returncode check **and** ffprobe output validation → explicit `RenderError`.
- **Honest failure on missing stub assets:** `RenderError` flows into the orchestrator's existing error boundary → `render: failed` (no fabricated success).

## Alternatives considered
1. **Import render.py functions directly** — rejected: couples SCOS to vendored internals, needs `sys.path` surgery, brittle to upstream changes. Subprocess keeps a clean black-box boundary.
2. **Reimplement an image-montage renderer in SCOS** — rejected: duplicates grade/loudnorm/concat the engine already does well; violates "no FFmpeg-logic duplication."
3. **Pre-convert stills via the engine** — not possible: the engine has no image-input path; the still→clip step must live in SCOS glue.

See `../adr/ADR-001-render-backend-adapter.md`.
