# 01 · Executive Summary

## The one-sentence reconstruction
`Download.mp4` is a **Mobile Legends multi-match kill compilation** by TikTok `@mark9m_`
that **disguises 6–9 different matches as one unstoppable run** by hiding every cut inside
identical map+HUD continuity and heavy in-game VFX — a **variable-ratio dopamine machine**
whose real craft is *clip curation, seam concealment, and ~9-second pacing*, not effects.

## How we proved it (not just observed it)
A naive scene-detection pass finds **zero cuts** (max scene-score 0.27 < 0.40). That is the
illusion. By extracting the **top-right HUD and reading the in-game timer + kill score at
each scene-peak**, the timeline exposes itself:

> 0:00 `02:16 5v0` → 0:15 `08:17 22v12` → 0:16 `10:22 10v12` → 0:43 `14:47 21v11`
> → 0:50 `14:54 23v12` → 0:53 `13:18 22v28` → 1:10 `17:21 27v21` → 1:41 `08:39 6v10`

Timers run *backwards* and scores *reset* — impossible within one match. The "no cuts"
finding flips into **"all cuts, perfectly masked"**, which reframes the entire system.

## The production system (creator's brain → 4 pillars)
1. **Curate:** best 8–11s kill highlight per match; drop anything without a payoff in 11s.
2. **Conceal:** cut on the brightest VFX frame; same hero/map/HUD keeps seams under
   scene-score 0.40 → the compilation reads as one heroic run.
3. **Pace:** flat-high comb — a reward/attention spike every ~9s (= 8-bar phrase at
   ~80–85 BPM), no valley deep enough to scroll, real speed for credibility.
4. **Convert:** continuous music carries the energy across hidden cuts, then a **hard
   silent black end card with `@handle`** trades replay for follow.

## Why viewers keep watching (psychology)
Variable, novel payoff every ~9s (slot-machine schedule) · power fantasy + competence
display made believable by the **authenticity layer** (full HUD, 1.0× speed, native VFX) ·
the live kill score is a built-in open loop ("how high does it go?").

## Biggest weakness (our opportunity)
It ships **16:9 landscape on a vertical feed** with **no text hook and no captions** —
~45% wasted screen and missed search signal. Fixing packaging (vertical reframe + hook +
trending sound) likely turns "good" into "viral-capable" **without changing the edit**.

## Deliverables produced (this folder)
Forensics · Timeline Map · Editing DNA · Retention Heatmap · Psychology · Creator Brain ·
Algorithm · Style Bible · **110 IF/THEN/BECAUSE rules** · 6 automation YAMLs
(style profile, editing, retention, psychology, timeline, blueprint) · Gap Analysis ·
Replication Accuracy · SCOS Recommendations.

## Replication accuracy
- **Now, from this one video: ~78%** (faithful, automation-ready clone).
- **After +3–5 more of the creator's videos + the live post + one master clip: ~92–94%.**

## Immediate SCOS action
Register `mark9m_mlbb` as a wf-2 montage preset; add the 5-assert QC gate; build the
**HUD-OCR boundary/kill detector** (the capability that cracked this case). See `14_*`.
