# ADR-001 — Stable RenderBackend interface + subprocess adapter over the vendored engine

- Status: Accepted
- Module: Stage 1 / Module 2 (Real FFmpeg Renderer)

## Context
The Stage-1 render stage was a stub. A production renderer already exists in the
vendored `integrations/video-use` engine (`helpers/render.py`, invoked via `vu.py`),
but (a) it is "byte-for-byte upstream except two Windows patches" and must not be
modified, and (b) the orchestrator's data model is stills + voiceover per scene,
which the engine (a video-cut tool) cannot ingest directly. SCOS must depend on a
stable renderer interface, not on engine internals, and must not duplicate FFmpeg
logic.

## Decision
Introduce a SCOS-owned renderer layer under `scos/render/`:
- `RenderBackend` ABC + typed request/result dataclasses — the stable interface the
  orchestrator depends on.
- `VideoUseBackend` — bridges stills+audio into per-scene clips and a video-use EDL,
  then invokes the engine **through its public CLI** (`vu.py render <edl> -o <out>`)
  as a **subprocess** (black box), and validates the output with ffprobe.

## Alternatives considered
1. **Import `render.py` functions directly.** Rejected — couples SCOS to vendored
   internals, requires `sys.path` surgery, brittle to upstream drift.
2. **Reimplement an image-montage renderer in SCOS.** Rejected — duplicates the
   engine's grade/concat/loudnorm/composite; violates "no FFmpeg-logic duplication."
3. **Have the engine convert stills.** Not possible — the engine has no image-input
   path; the still→clip step must be SCOS glue.

## Tradeoffs
- (+) Clean black-box boundary; engine stays unmodified; SCOS imports zero engine
  symbols; failures are surfaced and the output is validated.
- (−) One extra encode per scene (clip build) before the engine re-extracts
  ("double-encode"). Mitigated by building clips at the final canvas so the engine
  pass is light. A future optimization could emit engine-final clips and skip the
  re-extract.
- (−) Process-spawn overhead per render (negligible vs encode time).

## Reason
Maximizes reuse of production-proven code while keeping a stable, testable SCOS
interface and respecting the "do not modify the vendored engine" constraint.

## Impact
- New module `scos/render/{base,edl_bridge,video_use_backend,ffmpeg_engine}.py`.
- Orchestrator unchanged (same `ffmpeg_engine.render(input_data)` contract).
- Adding a different renderer later = implement `RenderBackend`; no caller changes.
