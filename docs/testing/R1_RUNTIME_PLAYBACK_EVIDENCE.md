# R1 Runtime Playback Evidence — HAIOS AI Video Studio

Baseline: `haios-ai-video-studio-r1.0.0`

This record preserves the runtime playback proof captured from the actually
launched Tauri application running on the official Microsoft WebView2 Fixed
Version Runtime (v151.0.4129.107), used to bypass a corrupted system
Evergreen registration. It is non-executable documentation only.

## Verdicts

APP_LAUNCH=PASS
AUTO_PLACE_CLIP=PASS
LOCAL_MEDIA_URL=PASS
VIDEO_LOADEDMETADATA=PASS
VIDEO_CANPLAY=PASS
VIDEO_PLAY=PASS
VIDEO_CURRENT_TIME_ADVANCES=PASS
VIDEO_PAUSE=PASS
VIDEO_SEEK=PASS
PLAYHEAD_SYNC=PASS
PREVIEW_PROXY_FALLBACK=PASS

## Observed in-app playback (real <video> element inside Fixed WebView2)

H264_CURRENT_TIME=1.561s+        (H.264/AAC MP4, direct preview)
PRORES_PROXY_CURRENT_TIME=1.56s+  (ProRes/PCM source -> H.264/AAC proxy preview)

## Proxy fallback

PRORES_PROXY_CODEC=H264/AAC
ORIGINAL_MEDIA_IMMUTABLE=TRUE

The ProRes/PCM source was probed, `previewNeedsProxy()` selected fallback,
`generate_preview_proxy` produced an H.264/AAC MP4 (verified by ffprobe),
and the proxy played through the Tauri-safe asset URL. The original source
media was not overwritten.

## Scope

- Resolved defects: RC1 (stale-snapshot import race -> atomic
  PLACE_PROBED_MEDIA + ADD_TRACK/REMOVE_TRACK), RC2 (raw Windows path in
  video.src -> centralized Tauri-safe URL resolver + asset protocol),
  RC3 (codec gaps / swallowed errors -> previewNeedsProxy + deterministic
  H.264/AAC proxy + PlaybackDiagnostics).
- Proof instrumentation (proofBridge / proof_config / proof_report) was
  removed before baseline sealing; it is NOT part of the shipped product.
