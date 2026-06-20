# Playbook — Fake Phone-UI Lyric Edit

> Editing skill distilled from the reference
> `input/reference/ScreenRecording_06-16-2026 6-19-51 PM_1.mp4` (an *Eenie Meenie*
> lyric edit built in After Effects, shown as a Wireframe/Result split screen).
> Goal of this file: let the OS reproduce this editor's style on demand. Working
> reference implementation: `work/uigen/build_lyric.py` (hot girl bummer edit).

## 1. The core mechanic (never skip this)

**Each lyric fragment becomes a believable phone-UI surface — the UI *is* the lyric.**
It is NOT "nice UI motion with captions on the side." The cleverness = wordplay between
what is sung and the UI that represents it.

> First attempt at this style failed because it copied the *surface* (UI cards on black)
> but missed the *mechanic*. Always state the mapping in one line per lyric before building.
> See memory: `feedback-reference-core-mechanic`.

Mapping recipe — for each lyric line ask "what phone moment would literally say this?":

| Lyric flavor | UI surface to fake |
|---|---|
| a name / single word | search bar, app label, a glowing blob with the word |
| talking to someone / "hi ___" | AI chat (Gemini/ChatGPT), iMessage thread |
| a list of traits/actions | to-do list / Reminders (strike items as sung) |
| "I'm done / through / over it" | progress bar to 100%, "Unsubscribe", call ending |
| money / buying | Apple Pay sheet, bank transfer, in-app purchase |
| a question | IG story poll, "you free?" text |
| hook / song title | music player now-playing + volume slider |
| time / a night | clock widget, lock screen, calendar |
| numbers / ranking | a list/leaderboard, "Share this story" |

## 2. Timing & cadence (measured from the reference)

- Vertical, **60 fps**, ~9:16, continuous (0 hard cuts — everything is animated transitions).
- **Cadence follows the vocal, not a fixed grid:**
  - **Verse / rapid-fire lyrics → swap UI every ~0.5–1.0 s** (measured: bursts at
    22.0, 22.8, 23.5, 24.0, 24.5, 25.0, 25.6, 26.4 s — roughly one UI per lyric phrase).
  - **Chorus / sustained line → hold ONE element 3–8 s** and animate *inside* it
    (volume rising, bar filling, shake on an accent word) instead of swapping.
- Snap every entrance/action to a **word onset**. Get onsets with word-level ASR
  (`work/uigen/transcribe.py`, openai-whisper `small`, downloads from OpenAI CDN).
- Per-word "hits" drive sub-animation: e.g. "you / you / you" → one BLOCKED stamp per
  onset; "through / through / through" → bar steps fuller on each.

## 3. Motion / easing (the "smooth" feel)

From the AE wireframes the editor animates **position + scale + a few degrees of rotation**
together with overshoot. Reproduce as:

- **Entrance:** ~0.18–0.22 s, `ease-out-back` (overshoot), scale 0.80→1.00, fade 0→1,
  slide up ~40–60 px. Snappy, not slow.
- **Exit:** ~0.12–0.15 s, scale →0.96, fade →0, slight slide.
- **Hold:** tiny float (`sin`) + a beat pulse so it never sits dead still.
- **Accent punch:** on each action onset add `+0.04–0.06 * exp(-dt*16)` to scale.
- **Tantrum/impact words:** brief positional shake `sin(t*70)*amp` with `amp = 18*exp(-(t-ts)*6)`.
- **Beat lock:** drive a background glow (and a micro card-punch) from the song's
  **amplitude envelope** (per-frame RMS of the audio), so motion is welded to the music.

## 4. Look

- Pure black background, single hero element centered, high contrast.
- Real iOS UI conventions: SF/Helvetica-ish (Arial Bold works), rounded glass cards
  `fill≈(28,28,30)` + 2px `(255,255,255,~30)` border, ~34–46 px corner radius.
- Color-emoji glyphs (`seguiemj.ttf`, `embedded_color=True`) — render emoji via the
  per-char rich-text helper, NOT plain `draw.text` (plain text = tofu boxes).
- A faux iOS **status bar** (9:41 + signal/wifi/battery) + a thin **progress bar**
  sells the "it's a real phone" illusion. Keep one small handle/watermark.
- Theme the accent to the song mood (hot-pink/red for "hot girl bummer").

## 5. Pipeline (our toolchain — no AE needed)

1. `transcribe.py` → word-level JSON for lyric onsets.
2. Choose a ≤60 s window (lead with the hook; a recognizable chorus beats a slow verse).
3. Extract that audio window to wav (envelope + final mux).
4. Build each UI surface as a Pillow RGBA card; cache by dynamic state `(scene, state)`.
5. Composite per frame: black bg → env-driven glow → transformed card → lyric caption
   (bold white + accent underline) → status bar + progress bar → handle. Pipe `rgb24`
   to ffmpeg (`libx264 -crf 19 -pix_fmt yuv420p`) muxing the audio. `-shortest`.
6. Censor profanity stylishly inside the UI (e.g. "f*** you" as a Recents/Block list).

## 6. QA checklist

- [ ] Every UI surface maps to a real lyric line (say the mapping out loud).
- [ ] Entrances land on word onsets; verse swaps fast, chorus holds + animates internally.
- [ ] No tofu glyphs (all emoji via rich-text helper).
- [ ] Motion has overshoot + beat-locked pulse; nothing sits static.
- [ ] ≤ 60 s, 1080×1920, audio synced, clean black, status/progress bar present.
- [ ] Render a few frames and actually *look* before declaring done.
