# 04 · Editing DNA (Phase 3)

Format per element: **WHAT · WHY · EMOTIONAL EFFECT · RETENTION EFFECT · HOW TO AUTOMATE**

---

## 1. The Invisible Cut (signature technique)
- **WHAT:** Cuts between different matches placed so frame-to-frame pixel delta stays
  low (scene-score ≤0.27, never trips 0.4). Achieved because every clip shares the same
  green map, same HUD layout, same hero — and cuts land *inside heavy VFX* (the kill
  flash at ~0:52 masks the seam to Match E).
- **WHY:** A visible hard cut every 9 s would feel choppy and "compilation-y". Hiding the
  seam makes 6–9 matches feel like **one god-tier continuous run**.
- **EMOTIONAL EFFECT:** Seamless competence — "this player never stops winning."
- **RETENTION EFFECT:** Removes the micro-exit that a visible cut invites; viewer never
  gets a "natural stopping point".
- **AUTOMATE:** Cut only between clips of the *same game/map/HUD*; place the cut on the
  brightest VFX frame (max luma spike) or a screen-flash; cross-dissolve 2–4 frames if
  pixel delta would exceed threshold.

## 2. Cold Open (no intro)
- **WHAT:** Frame 1 is gameplay; first fight within 8 s; zero title card.
- **WHY:** TikTok judges the first 1–2 s; a logo/title spends the hook budget on nothing.
- **EMOTIONAL:** Instant immersion.
- **RETENTION:** Maximizes 1-/3-second retention (the metrics the algo weights most).
- **AUTOMATE:** Open on the highest-action pre-roll clip; never prepend branding.

## 3. Punch-In Zoom (only "camera" move)
- **WHAT:** ~1.15–1.30× scale push toward the action during teamfights/kills, easing back
  on lulls. Evidence: screen-fixed HUD (minimap, skill buttons) is visibly larger/edge-
  cropped at 0:48/0:50/0:90 vs the wider baseline at 0:00.
- **WHY:** Mobile gameplay is small/busy; the punch directs the eye to the kill.
- **EMOTIONAL:** Intensity, "lean in".
- **RETENTION:** Re-spikes attention each clip; a pseudo-cut without a real cut.
- **AUTOMATE:** `scale 1.0→1.25` keyframes centered on the player hero; trigger on
  kill-event / ≥3 enemies / ult-cast; release over ~0.5 s after.
- **CONFIDENCE:** dynamic (not constant) = MEDIUM-HIGH; exact factor = MEDIUM.

## 4. Speed = 1.0× always
- **WHAT:** No speed-ramp, slow-mo, or reverse. 30fps native throughout.
- **WHY:** Mechanics (combos, dodges) read as skill only at real speed; ramps would hide
  the competence being sold.
- **EMOTIONAL:** Authenticity / "no tricks".
- **RETENTION:** Trust → longer watch.
- **AUTOMATE:** Lock timescale 1.0; forbid ramp nodes.

## 5. In-game VFX as the only effects layer
- **WHAT:** Every glow, AOE ring, particle, "Kill"/"Immune"/"Ultimate" banner, floating
  damage/gold number is **MLBB's own UI** — no editor-added flashes, shakes, CA, vignette.
- **WHY:** The game already ships dopamine-grade VFX; adding more buries the read.
- **EMOTIONAL:** Clean spectacle.
- **RETENTION:** Legible action = sustained comprehension = sustained watching.
- **AUTOMATE:** Add zero post-VFX; instead *select clips* where in-game VFX peaks.

## 6. HUD kept fully intact
- **WHAT:** Minimap, timer, kill score, KDA, skill buttons (Thai), spells all visible.
- **WHY:** HUD = proof of authenticity + live score = built-in progress bar.
- **EMOTIONAL:** Credibility, stakes.
- **RETENTION:** Rising score is an open loop ("how high does it go?").
- **AUTOMATE:** Never crop out timer/score; frame so top-right + bottom HUD survive.

## 7. Color = native
- **WHAT:** Dark, saturated MLBB palette; neon skill accents on deep green. No film LUT.
- **WHY:** Game art is already feed-legible; grading adds cost, risks muddying VFX.
- **AUTOMATE:** Optional +5% contrast/sat, light sharpen post-upscale; no creative LUT.

## 8. Sound design = bed + baked SFX
- **WHAT:** One ~80–85 BPM track, drop on frame 1, runs to 1:55.7, then silence.
- **WHY:** Music carries energy across invisible cuts (audio continuity hides video seams).
- **EMOTIONAL:** Momentum, hype.
- **RETENTION:** Continuous audio = no auditory "stop" cue mid-video.
- **AUTOMATE:** Lay one track, align beat-1 to frame-1, hard-cut audio at end card.

## 9. End-card hard stop
- **WHAT:** Black + TikTok + `@username` search bar + **dead-air** for 3 s.
- **WHY:** A silent black frame is a pattern interrupt that says "decide now" → follow.
- **EMOTIONAL:** Mild withdrawal → action.
- **RETENTION/CONVERSION:** Trades replay for follow.
- **AUTOMATE:** Template end card; pull `@handle` from profile; mute audio.

## Cut-rhythm summary
- Clip length: **8–11 s** (one highlight per clip).
- Cut style: **0% visible hard cuts, 100% masked/soft** (within-game continuity).
- Transitions: none decorative; seams hidden in VFX or via tiny dissolves.
- Pacing curve: **flat-high** (front-loaded, no build/decay) — anti-scroll, not narrative.
