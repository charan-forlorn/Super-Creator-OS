# 02 · Forensics Report (Phase 1)

## Container & streams (ffprobe, probe_score=100)

| Field | Value | Interpretation |
|---|---|---|
| Duration | **118.667 s** (1:58.7) | Video 118.667 / audio 118.655 — locked |
| Resolution | **1024 × 576** | Sub-HD; likely 720p source bilinear-shrunk by platform |
| Aspect ratio | **16:9** (DAR 16:9, SAR 1:1) | **Landscape, NOT 9:16** — desktop/landscape-feed oriented |
| FPS | **30 / 1 constant** | 3,560 video frames |
| Video codec | H.264 **High@L3.1**, yuv420p, 8-bit | `has_b_frames=2` (2 B-frames) |
| Video bitrate | **2.43 Mbps** | Moderate; fine for flat UI + green map |
| Audio codec | **AAC-LC**, stereo, 44.1 kHz, 128 kbps | `fltp`, 5,113 frames |
| Overall bitrate | 2.56 Mbps · file 38.0 MB | — |
| Color | primaries **bt470bg**, transfer/matrix **smpte170m**, **TV range** | BT.601 SD pipeline (not BT.709) → SD provenance |
| Chroma | yuv420p, left-sited | Standard consumer |

## Platform / provenance indicators
| Signal | Value | Meaning |
|---|---|---|
| `encoder` | `Lavf58.76.100` | FFmpeg/Lavf — ByteDance server-side re-encode |
| `TAG:comment` | `vid:v14044g50000co6i79nog65or36fdudg` | **TikTok/Douyin internal video id** |
| `TAG:vid_md5` | `830fad35fe851dba2ed27af15a44425d` | Platform content hash |
| `TAG:aigc_info` | `{"aigc_label_type":0}` | **AI-generated/assisted content label** present |
| Burned overlay | TikTok logo + `@mark9m_`, **bouncing** position | Native TikTok export watermark (anti-rip) |
| End card | TikTok logo + search-bar `@ mark9m_` | TikTok "profile CTA" template |

## AI-generation indicators
- `aigc_label_type:0` is **explicitly stamped** → some AI tool touched this asset.
- Gameplay itself is real MLBB capture (HUD/timer/score are internally consistent
  *within* each clip). The AI label most plausibly comes from an **AI upscaler /
  enhancer / auto-editor** in the pipeline, not synthetic footage.
- **Confidence:** AI label real = HIGH; "footage is real gameplay, AI = post-enhance" = MEDIUM-HIGH.

## Compression indicators
- Double-compression signature: SD color pipeline (BT.601) + Lavf re-encode + 1024×576 →
  source was **re-encoded at least twice** (capture → upload → platform export).
- 2.43 Mbps over a busy particle scene = visible mosquito noise around VFX (acceptable for feed).

## Audio structure (RMS envelope, 1 s windows)
| Window | Level | Event |
|---|---|---|
| 0.00–0.50 s | −39 → −33 dB | Fade-in |
| ~0.70 s | jump to −15 dB | **Music drop / track starts** (lands on cold-open) |
| 0.70–115.7 s | −12 to −16 dB | Continuous music bed + sub-mixed game SFX |
| **115.71–118.68 s** | silence (−∞) | **End card, ~3 s dead-air** |

- Tempo: transient spacing ≈ 0.70–0.75 s → **~80–85 BPM half-time** (hip-hop/phonk feel). Confidence: MEDIUM.
- Game SFX (hit/kill/skill) baked into the bed — not a separate stem.

## Forensic verdict
A **TikTok-exported, AIGC-labeled, 16:9 / 30fps / ~119s MLBB montage**. SD provenance,
platform re-encode, native bouncing watermark, profile-CTA end card. Nothing here is a
master file — treat as a *reference/style donor*, not an editable source.
