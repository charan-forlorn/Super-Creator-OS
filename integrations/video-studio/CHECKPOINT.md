# HAIOS AI Video Studio — R2 Operator Checkpoint

PROGRAM=HAIOS AI Video Studio → R2 Production Editor Expansion
R1_BASELINE=34e4e2ee795922448411a79a7d268fd9f8bc5828
R1_TAG=haios-ai-video-studio-r1.0.0
R2_2_HEAD=fcce33bf20ae (R2.2 sealed parent)
R2_3_COMMIT=THIS_COMMIT (the commit containing this checkpoint)

## MILESTONE STATUS
R2_0=PASS
R2_1=PASS
REAL_GUI_RUNTIME=PASS
R2_2=PASS (S1 R2.2 PREVIEW + MEDIA FOUNDATION — 7/7 real-GUI gates + full proxy miss/hit/reuse chain)
R2_3=PASS (S2 MEDIA WORKSPACE - real GUI + full regression verified)
R2_4=PASS (RECONSTRUCTED scope: Text & Caption Workspace; original prior R2.4 spec not recoverable)
R2_5..R2_7=UNSPECIFIED_IN_REPO (reconstruct only from capability-gap evidence)
CRITICAL_DEFECTS=0

## S1 R2.2 — VERIFIED REAL-GUI EVIDENCE (full harness run, tauri-driver :4444)
FULL_S1_GUI=7/7 PASS
  GUI_CLIPS_VISIBLE=PASS
  PREVIEW_PLAYBACK=PASS
  PLAYHEAD_SYNC=PASS
  VIDEO_SEEK=PASS
  CLIP_BOUNDARY_PLAYBACK=PASS
  THUMBNAIL_CACHE=PASS
  PROXY_CACHE=PASS
PROXY CHAIN (real production command, miss→create→ffprobe→hit/reuse):
  PROXY_DECISION_H264_AAC=PASS        (previewNeedsProxy({h264,aac})===false)
  PROXY_REQUIRED_FIXTURE=sample_prores.mov
  PROXY_CORRECTLY_SKIPPED=PASS        (H.264/AAC takes direct playback, no proxy file)
  PROXY_CACHE_MISS=PASS
  PROXY_CREATED=PASS
  PROXY_FFPROBE=PASS                  (proxy verified H.264/AAC/mp4 via ffprobe)
  ORIGINAL_SOURCE_IMMUTABLE=PASS      (size+mtime unchanged after cache ops)
  PROXY_CACHE_HIT=PASS
  PROXY_CACHE_REUSE=PASS
MEDIA_ERROR_HANDLING=PASS
REAL_GUI_RUNTIME=PASS

## ROOT CAUSES FIXED (this session)
RESIZE_1 (PROXY_CACHE fail): proxy dir never created because the seed's
  `await ensureThumbnail` hung the detached loop. Root cause = ffmpeg/ffprobe
  spawned by the Rust media commands used default INHERITED stdio; in the bundled
  GUI-subsystem app (no console) those stdio handles are invalid → ffmpeg blocks.
  FIX: `ffcmd()` in src-tauri/src/bridge.rs sets Stdio::null() for stdin+stderr
  (stdout piped for ffprobe JSON); all 5 production ffmpeg/ffprobe spawn sites use it.
RESIZE_2 (ffmpeg not found under WebDriver launch): tauri-driver spawns the app
  with a minimal PATH, so `which("ffmpeg")` failed. FIX: `which()` now also probes
  well-known Windows install dirs (scoop shims, C:\ffmpeg\bin, etc.) before giving
  up. Harness additionally injects scoop shims dir onto PATH via tauri:options.env.

## STACK (as committed)
S0 CURRENTNESS=PASS
S1 R2.2 PREVIEW + MEDIA FOUNDATION:
  - packages/media-engine/src/cacheKey.ts: deterministic proxy/thumbnail cache keys
  - packages/media-engine/src/cache.ts: PureMediaCache lifecycle (no fs IO, browser-safe)
  - packages/media-engine/tests/cache.test.ts + preview-proxy.test.ts: PASS
  - apps/desktop/src-tauri/src/bridge.rs: ensure_preview_proxy / ensure_thumbnail /
    invalidate_cache (managed cache dir under LOCALAPPDATA/haios-video-studio);
    ffcmd() stdio fix; which() discovery fallback; ensure_preview_proxy_impl seam;
    #[cfg(test)] ensure_preview_proxy_real_miss_hit_reuse test
  - apps/desktop/src-tauri/src/lib.rs: 3 Tauri commands registered (no new test bridge)
  - store: cacheState + recordProxyCache/recordThumbnailCache/invalidateSourceCache
  - MediaPanel: cache-aware ensure_* commands
  - e2e/run-r2.2-preview.mjs: real-GUI S1 gate runner (PERMANENT test infra)
  - e2e/fixtures/project.json: H.264 (asset-fixture) + ProRes/PCM (asset-prores) w/ codecs
  - tests/fixtures/gen_prores.mjs: ProRes/PCM generator (gitignored *.mov)
  - src/e2e-entry.tsx: render-first e2e seed → detached thumbnail+proxy via REAL commands
RUST TESTS=4 PASS (3 cache contract + 1 real miss/hit/reuse)
PACKAGE TESTS=PASS (desktop 25/25 incl E2E-01 19/19; media-engine incl Phase A)
TYPECHECK=PASS
CARGO_BUILD_RELEASE=PASS
NORMAL_PRODUCTION_E2E_HOOK_REFERENCES=0 (no new production proof bridge added)

## S2 R2.3 - VERIFIED MEDIA WORKSPACE EVIDENCE
FULL_S2_GUI=8/8 PASS
  BACKGROUND_ANALYSIS_NON_BLOCKING=PASS
  MEDIA_BIN=PASS
  THUMBNAILS=PASS
  METADATA=PASS
  WAVEFORM=PASS
  MISSING_MEDIA_DETECTION=PASS
  MEDIA_RELINK_UI=PASS
  REAL_GUI_RUNTIME=PASS
R2_2_BACKWARD_REGRESSION=PASS
  PREVIEW_PLAYBACK=PASS
  PLAYHEAD_SYNC=PASS
  VIDEO_SEEK=PASS
  CLIP_BOUNDARY_PLAYBACK=PASS
  THUMBNAIL_CACHE=PASS
  PROXY_CACHE=PASS (MISS -> CREATE -> FFPROBE -> HIT -> REUSE)
  ORIGINAL_SOURCE_IMMUTABLE=PASS
R2_3_COMMAND_TESTS=PASS (media.relink 2/2; store relink undo/redo 2/2)
R2_3_ANALYSIS_TESTS=PASS (bounded queue + analysis 3/3)
RUST_TESTS=5/5 PASS (includes real waveform and proxy cache lifecycle)
DESKTOP_TESTS=30/30 PASS (includes E2E-01 19/19)
FULL_PNPM_TEST=PASS
FULL_TYPECHECK=PASS
PACKAGE_BUILD=PASS
PRODUCTION_FRONTEND_BUILD=PASS
PRODUCTION_TAURI_RELEASE_BUILD=PASS
FINAL_E2E_TAURI_RELEASE_BUILD=PASS
DIFF_CHECK=PASS
ENCODING_RECONCILIATION=PASS (no new suspicious-byte delta)
CRITICAL_DEFECTS=0

## R2.3 IMPLEMENTATION
- mediaAnalysis.ts: bounded derived-media analysis queue, max concurrency=2
- MediaPanel: non-blocking media bin analysis, metadata, waveform, missing state, Relink UI
- command-system media.relink: undoable, kind-safe, clip-compatibility fail-closed
- store: runtime-only analysis state; cache invalidation on relink/undo/redo
- Rust/Tauri: deterministic waveform PNG cache with real ffmpeg MISS/HIT reuse test
- E2E: deterministic missing-media fixture + real WebDriver R2.3 gate runner
- Production project schema unchanged; derived analysis remains runtime-only


## R2.4 RECONSTRUCTED TEXT & CAPTION WORKSPACE
SCOPE_AUTHORITY=RECONSTRUCTED_FROM_REPO_CAPABILITY_GAPS
ORIGINAL_R2_4_SPEC_RECOVERED=FALSE
CAPTION_PLACE_COMMAND=PASS (deterministic text track + caption id + atomic undo/redo)
AI_ADD_CAPTION_ROUTE=PASS (canonical caption.place seam; former payload mismatch closed)
CAPTION_STORE=PASS (add/delete through CommandBus only)
CAPTION_WORKSPACE_UI=PASS (composer + duration + list + delete)
CAPTION_PREVIEW_OVERLAY=PASS
R2_4_REAL_GUI=PASS (add -> overlay -> delete -> undo restore)
COMMAND_SYSTEM_TESTS=33/33 PASS
AI_CORE_TESTS=9/9 PASS
DESKTOP_TESTS=32/32 PASS
DESKTOP_TYPECHECK=PASS
R2_3_GUI_REGRESSION=PASS
R2_2_GUI_REGRESSION=PASS
CRITICAL_DEFECTS=0

## R2.5 RECONSTRUCTED AUDIO WORKSPACE + SOURCE AUDIO PRESERVATION
SCOPE_AUTHORITY=RECONSTRUCTED_FROM_REPO_CAPABILITY_GAPS
ORIGINAL_R2_5_SPEC_RECOVERED=FALSE
CLIP_AUDIO_MODEL=PASS (legacy-safe defaults gainDb=0, muted=false)
CLIP_AUDIO_COMMAND=PASS (undoable gain/mute, fail-closed -60..0 dB)
AUDIO_WORKSPACE_UI=PASS (Inspector gain + mute controls)
PREVIEW_SOURCE_AUDIO=PASS (default unmuted; dB -> linear volume; mute/undo verified)
EXPORT_SOURCE_AUDIO=PASS (embedded audio preserved; mute/gain applied; no-audio fallback stays silent)
OUTPUT_AUDIO_NON_SILENT=PASS (real ffmpeg + volumedetect)
R2_5_REAL_GUI=PASS (unmuted -> mute -> undo -> -12 dB gain)
PROJECT_MODEL_TESTS=14/14 PASS
COMMAND_SYSTEM_TESTS=35/35 PASS
DESKTOP_TESTS=33/33 PASS
RUST_TESTS=7/7 PASS
E2E_EXPORT=20/20 PASS
DESKTOP_TYPECHECK=PASS
PRODUCTION_FRONTEND_BUILD=PASS
PRODUCTION_TAURI_RELEASE_BUILD=PASS
FINAL_E2E_TAURI_RELEASE_BUILD=PASS
R2_4_GUI_REGRESSION=PASS
R2_3_GUI_REGRESSION=PASS
R2_2_GUI_REGRESSION=PASS
CRITICAL_DEFECTS=0

## NEXT EXACT ACTION
Reconstruct R2.6 from the next highest production-editor capability gap using repo evidence only.
Do not infer reconstructed milestones are the original spec.
BLOCKERS=none

## R2.6 RECONSTRUCTED VISUAL TRANSFORM & COMPOSITION WORKSPACE
SCOPE_AUTHORITY=RECONSTRUCTED_FROM_REPO_CAPABILITY_GAPS
ORIGINAL_R2_6_SPEC_RECOVERED=FALSE
CLIP_TRANSFORM_COMMAND=PASS (scale/x/y/opacity + atomic undo/redo)
TRANSFORM_STORE=PASS
TRANSFORM_INSPECTOR_UI=PASS
PREVIEW_TRANSFORM_FIDELITY=PASS
EXPORT_TRANSFORM_FILTER=PASS
REAL_FFMPEG_TRANSFORM_FILTER=PASS
R2_6_REAL_GUI=PASS
COMMAND_SYSTEM_TESTS=37/37 PASS
DESKTOP_TESTS=34/34 PASS
RUST_TESTS=9/9 PASS
R2_5_GUI_REGRESSION=PASS
R2_4_GUI_REGRESSION=PASS
R2_3_GUI_REGRESSION=PASS
R2_2_GUI_REGRESSION=PASS
PRODUCTION_TAURI_RELEASE_BUILD=PASS
FINAL_E2E_TAURI_RELEASE_BUILD=PASS
CRITICAL_DEFECTS=0

## NEXT EXACT ACTION
Reconstruct R2.7 from the next highest preview/export fidelity gap.
Current highest gap: caption burn-in/export fidelity.
Do not infer reconstructed milestones are the original spec.
BLOCKERS=none
