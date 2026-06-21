# 14 · Recommendations for Super Creator OS

Gated through the SCOS v4 Operating Charter: each item ties to retention/quality and
respects the priority hierarchy. Ranked by impact-per-effort.

## P0 — Implement now (high impact, low effort)
1. **Register `mark9m_mlbb` as a wf-2 montage style-preset.** Wire
   `automation/creator_style_profile.yaml` + `editing_rules.yaml` into the existing
   montage assembler (the repo already does multi-shot beat-synced montage per git log).
   *Win:* one-command generation in this proven style.
2. **Add the QC gate** (`editing_rules.qc_gate`): assert `scene_score_max<0.40`,
   `reward_gap<=11s`, `music_unbroken_until_endcard`, `hud_score_visible`,
   `endcard_silent_with_handle`. Reject+log on fail. *Win:* guarantees the signature
   seamlessness automatically.
3. **HUD-OCR boundary detector.** OCR top-right timer+score to detect match boundaries
   and kill events. This is the single most useful new capability — it's what cracked
   this analysis. *Win:* automatic highlight + seam detection from raw recordings.

## P1 — High value, medium effort
4. **Masked-concat module.** Place cuts on max-luma VFX frames; auto-dissolve when pixel
   delta >0.30. Turns "compilation" into "one god run".
5. **Punch-in keyframer.** Trigger 1.0→1.25 zoom on kill/3+enemies/ult, ease out on lull,
   clamp 1.30, protect score HUD.
6. **Vertical reframe (9:16).** Biggest distribution fix — the reference *leaked* by
   shipping 16:9 on a vertical feed. Keep hero + right-side HUD. Dual-export 16:9 master
   for YouTube.

## P2 — Differentiators (test against the reference's gaps)
7. **Add a 1–2s text hook** in the cold open (reference has none) — A/B for retention+search.
8. **Trending-sound selector** by mood (phonk/hiphop, 80–85 BPM) instead of a static bed.
9. **Caption/hashtag generator** (hero + game + rank keywords) — reference shipped none.

## Charter alignment notes
- These *extend* the existing wf-2 pipeline (don't destabilize working code) — preset +
  modules, not a rewrite.
- The cleanup of `input/raw` after this job is gated by the standing authorization
  (output + memory + archive first). This analysis is an artifact, not a render job, so
  no auto-delete is triggered yet for `Download.mp4` — it remains as the reference donor
  until a render+archive completes.

## Suggested memory to persist (reusable across future jobs)
A `reference` memory: *"mark9m_ MLBB montage style = multi-match invisible-cut kill comp,
8–11s clips, cold open, full HUD, real speed, native VFX, continuous ~80-85bpm bed →
silent @handle end card. Profile at analysis/REF_mark9m_mlbb/."* (Write on request.)
