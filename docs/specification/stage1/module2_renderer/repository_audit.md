# Module 2 — Real FFmpeg Renderer · Phase 1: Repository Audit

> Read-only audit. Evidence-based; every claim cites a repo file. No files modified.

## Executive summary
The live pipeline shipped a **non-functional render stub** at `scos/render/ffmpeg_engine.py`: it built an ffmpeg argv list and returned a fabricated `video_path` but **never invoked ffmpeg**. A **complete, production-grade local renderer already exists** at `integrations/video-use/engine/helpers/render.py` (662 LOC), invoked via the `integrations/video-use/vu.py` CLI shim. Module 2 is therefore a **reuse + bridge + abstraction** task, not a green-field build.

## Current render flow (two paths that did not meet)
- **Orchestrator path (stubbed):** `script → scene_plan → asset_build → edit_plan → render(stub) → qa`. The stub returned a promised path without producing a file (`scos/core/orchestrator.py:57`).
- **video-use path (real, not wired):** `timeline_to_edl → edl.json → vu.py render → render.py → final.mp4 → render_to_memory`.

## Data-model finding (decisive)
The orchestrator's true render input is **stills + audio**, not video cuts:
- `scos/agents/asset_builder.py:19-20` emits a `.png` + `.wav` per scene (currently nonexistent stub paths).
- `scos/agents/edit_composer.py:14-22` turns those into `clips[].asset_path/audio_path` with output-timeline `start/end`.
The vendored engine (`render.py`) cuts ranges from **video** sources and cannot ingest stills directly — so a still→clip bridge is required.

## Three EDL/timeline dialects
- **D1 Orchestrator:** `{clips:[{scene_id,start,end,asset_path,audio_path}], total_duration}` — `edit_composer.py`.
- **D2 video-use EDL:** `{sources:{name:path}, ranges:[{source,start,end,grade…}], grade, overlays, subtitles, total_duration_s}` — `integrations/adapter/timeline_to_edl.py:188-197`, consumed by `render.py`.
- **D3 WF-1 highlight:** `{source:str, ranges:[{start,end,label,kind}]}` — archived `edl.json` (shortgen/montage; out of scope).

## Reuse classification
| Component | Decision | Why |
|---|---|---|
| `helpers/render.py` (via `vu.py`) | Reuse with wrapper (subprocess) | Production pipeline; vendored "byte-for-byte upstream except 2 patches" (`integrations/README.md`) → invoke, don't edit. |
| `helpers/grade.py` | Reused inside engine | Engine dependency; not called directly by SCOS. |
| `timeline_to_edl.py` EDL shape | Mirror | Canonical D2 schema to emit. |
| `render_to_memory.py` | Out of scope (learning loop) | Untouched. |
| stub `ffmpeg_engine.py` | Replace | The Module-2 target. |
| shortgen/montage/highlight | Do not touch | Stage-2 / non-renderer. |

## Gaps vs production goals
Real ffmpeg invocation ❌ · renderer abstraction ❌ (hard import) · GPU detection ❌ (libx264-only) · structured logging ❌ (`print`) · retry/backoff ⚠️ ad-hoc · output validation ⚠️ post-hoc only · determinism unverified.

## Risks
Dialect fragmentation; editing the vendored engine; Windows filtergraph drive-colon hazard (patched in `grade.py:106`, `render.py:543`); **render.py has 0 tests** (`production_readiness_audit.md` R-4); ffmpeg assumed on PATH; the stub recorded a render that never happened.

## Files that must NOT be modified
Vendored engine internals (`integrations/video-use/engine/**`), Stage-2 modules (`integrations/shortgen|highlight`), learning/memory (`integrations/learning`, `memory/`, `scos/memory`), `input/reference/` policy, `README.md`, git config/history.

## Conclusion
Replace the stub with a thin SCOS-owned renderer interface plus a backend that bridges stills+audio into the existing engine over its public CLI. No engine edits; no logic duplication.
