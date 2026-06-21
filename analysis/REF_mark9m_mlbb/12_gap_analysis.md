# 12 · Gap Analysis (Phase 11)

## What we know with high confidence
- Format/codec/metadata (ffprobe — exact).
- Multi-match stitch with invisible cuts (proven by timer/score discontinuity).
- Cold open, ~8–11s clips, flat-high pacing, real speed, native VFX, full HUD.
- Audio bed continuous → silent end card; CTA template.

## What is still missing (blocks perfect replication)

| Gap | Why it matters | How to close |
|---|---|---|
| **Exact seam timestamps** | We located ~7 boundaries via scene-peaks + verified 5 by HUD; the other ~2 are inferred. | OCR the HUD timer/score every 0.5s across the whole file → exact cut frames. |
| **Exact punch-in curve** | Zoom is confirmed dynamic but factor/easing is estimated (1.15–1.30). | Pixel-track a fixed HUD element (skill button) frame-by-frame → measure scale over time. |
| **Music identity & BPM** | "Trending sound" is a major algo lever; BPM only estimated (~80–85). | Audio-fingerprint the bed (Shazam/ACRCloud); run a beat-tracker for true BPM. |
| **Caption / hashtags / posting copy** | Not in the file; drives search + comments. | Pull from the live TikTok post (URL/handle). |
| **True source resolution** | File is 1024×576 platform export; original may be 1080p+. | Get the creator's master, or infer from a higher-quality re-upload. |
| **Whether AI touched footage vs just enhanced** | `aigc_label_type:0` is ambiguous. | Compare against the creator's known workflow; inspect for upscale artifacts. |
| **Clip-selection criteria internals** | We infer "best kill per match"; exact thresholds unknown. | Gather 5–10 of the creator's videos → learn the selection distribution. |
| **Watermark policy** | Native TikTok mark suggests re-download, not original master. | Confirm provenance; decide reframe-out vs keep. |

## What prevents perfect replication right now
1. No frame-exact seam/zoom ground truth (estimated, not measured).
2. No music ID (can't reuse the exact sound).
3. Single specimen — style generalization is inferred from one video.
4. No post-copy/engagement data (can't validate algo hypotheses).

## Highest-leverage data to collect next
1. **3–5 more @mark9m_ videos** → turns inferences into a learned distribution (biggest gain).
2. **The live post** (caption, hashtags, sound name, view/like/share stats).
3. **One master-quality clip** → exact zoom + seam measurement.
