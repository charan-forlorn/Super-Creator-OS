# Cross-Video Consistency Report — mark9m (MLBB)

> **Verdict: VALIDATION BLOCKED — promotion DENIED. Status remains `Observed Style`.**
> The study cannot proceed past Phase 1 (Video Collection) because the required
> corpus of 3–5 *additional published* mark9m videos **does not exist in the workspace**.
> Current verifiable corpus of *published edits* = **1 video** (`Download.mp4`).
> Consistency across a sample of one is mathematically undefined. No fabricated
> profiles were created.
>
> **See ADDENDUM A (2026-06-21) at the end** — a corpus update was attempted; the
> added files were one duplicate of the original and one *raw single-match replay
> capture* (not a published edit, mark9m attribution unconfirmed). Verdict unchanged.

- **Date:** 2026-06-21
- **Analyst posture:** forensic / falsification-first (attempt to *disprove*, per task)
- **Original hypothesis under test:** mark9m = "Hidden Match Montage" archetype; core
  system Curate → Conceal → Pace → Convert; reward interval ≈ 9s; BPM 80–85;
  standardized silent `@handle` end card. Prior confidence **78% (Observed Style)**.

---

## 1. Executive Summary

The task requires validating a single-video hypothesis against 3–5 **additional**
videos from the same creator and promoting to *Verified Creator Framework* only if
cross-video consistency ≥ 85%.

A full inventory of the workspace finds **only one mark9m artifact** — the original
reference `Download.mp4`. Both on-disk copies are byte-identical:

```
24dda92f6818d122201c205b4c6544a7  input/raw/Download.mp4
24dda92f6818d122201c205b4c6544a7  input/reference/Download.mp4
```

Every other file in `input/reference/` was checked and ruled out (see §2). None is a
published mark9m MLBB video.

Because validation is, by definition, a **repeatability** measurement, a corpus of
n=1 produces **no measurable consistency**: variance is undefined, drift is
unobservable, and "repeatable / intentional / consistent" cannot be distinguished
from "single-video artifact" — which is precisely the failure mode the study exists
to catch. **The honest forensic result is therefore non-promotion**, not a score.

This is not a soft fail. A falsification framework that promotes on n=1 would promote
*any* one-off as a "verified system." Refusing to do so is the framework working
correctly.

---

## 2. Validation Methodology

**Step 1 — Corpus assembly (where the study stopped).** Enumerated `input/` and
`analysis/`. Identified candidate videos, then probed each to confirm game, creator,
and whether it is a *published edit* (required to study editing/concealment/end-card
DNA) versus a raw capture.

| Candidate file | Probe result | mark9m MLBB published edit? |
|---|---|---|
| `input/raw/Download.mp4` | the original reference | ✅ **yes — n=1** |
| `input/reference/Download.mp4` | md5-identical duplicate of the above | ⟲ same file, not independent |
| `Highlight …riarix.webm` | 1080×1920, 28.8s — **ROV** (Arena of Valor) by creator **riarix** | ❌ different game + different creator |
| `IT HURTS …animation.webm` | sad-animation vent short | ❌ not gameplay |
| `Riley, You Okey …animation.webm` | animation short | ❌ not gameplay |
| `ScreenRecording_06-16-2026 …mp4` | 920×1472, 56s — window screen capture | ❌ raw capture, unattributed |
| `การบันทึกหน้าจอ 2026-06-15 …mp4` | 1744×982, 54s — desktop capture | ❌ raw capture, unattributed |
| `การบันทึกหน้าจอ 2026-06-16 …mp4` | 1782×1004, 258s — desktop capture | ❌ raw capture, unattributed |
| `ที่เที่ยวเชียงคาน …travel …webm` | travel short | ❌ not gameplay |

**Step 2 — Per-video profiling (Phase 1 deliverables):** NOT PRODUCED. Generating
`video_profile.md` for videos that do not exist would be fabrication and is refused.

**Steps 3–7 (Phases 2–7):** NOT EXECUTED. Each depends on ≥2 independent videos
(hidden-cut matrix needs cross-video cut patterns; reward-interval/BPM stats need a
distribution; end-card and drift comparison need multiple specimens). With n=1 every
one of these reduces to "restate the single-video finding," which is not validation.

**Anti-fabrication control:** No synthetic timestamps, BPMs, intervals, or confidence
numbers were invented for non-existent videos. Per project guardrails, outcomes are
reported faithfully even when the result is "blocked."

---

## 3. Hidden Cut Findings (cross-video)

**Not assessable.** The hidden-cut hypothesis (concealed seams at VFX peaks, scores
running backwards, HUD timer resets) is *strongly supported within `Download.mp4`*
per the prior forensic pass — but a within-video finding is exactly what the original
78% already captured. Whether mark9m **consistently and intentionally** conceals cuts
across his catalog is **unknown** and cannot be inferred from one specimen.

---

## 4. Reward Interval Findings (cross-video)

**Not assessable.** The ≈9s reward-interval hypothesis has, at present, a sample of
**one video's** intervals. No average / median / min / max *across videos* can be
computed. A single video cannot tell us whether 9s is a creator constant or a
coincidence of this upload.

---

## 5. BPM Findings (cross-video)

**Not assessable.** 80–85 BPM is a one-video estimate. Cross-video BPM consistency is
undefined for n=1.

---

## 6. Conversion System Findings (cross-video)

**Not assessable.** The silent-black `@handle` end card appears once. "Standardized
conversion system" is a claim about repetition; repetition needs ≥2 specimens.

---

## 7. Style Drift Findings

**Not assessable — drift requires ≥2 points.** Drift (editing / psychology /
retention) is a *difference between videos*. With one video there is nothing to
difference against. Cannot classify LOW / MEDIUM / HIGH.

---

## 8. Framework Confidence Score

Consistency scores measure agreement across the corpus. With n=1 there is no
agreement to measure, so each sub-score is reported as **N/A (undefined)**, not 0 and
not 100. Reporting a number here would be manufacturing a measurement.

| Dimension | Cross-video consistency | Note |
|---|---|---|
| Hidden Cut System | **N/A** | strong *within* `Download.mp4`; cross-video unmeasured |
| Reward System | **N/A** | single interval set |
| Pacing System | **N/A** | single specimen |
| Conversion System | **N/A** | one end card observed |
| Editing DNA | **N/A** | no second specimen |
| Psychology DNA | **N/A** | no second specimen |
| **Overall Framework Confidence (cross-video)** | **N/A — corpus insufficient** | |

> Note: the **single-video** descriptive confidence remains **~78% (Observed Style)**
> from the prior pass. That number is unchanged by this study — it was never a
> cross-video number and this study added no new videos.

---

## 9. Promotion Decision

**DENIED.** Promotion rule requires overall cross-video consistency ≥ 85%. The
measured value is **undefined (N/A)** because the corpus is n=1. Undefined does not
satisfy ≥85%.

```
mark9m_mlbb : Observed Style  →  Observed Style   (NO CHANGE)
```

This is the correct, conservative outcome of a falsification-first protocol: a
hypothesis that has *not yet been exposed to disconfirming evidence* (additional
videos) cannot be called "verified." It has simply not been tested.

---

## 10. Memory Registration Recommendation

**DO NOT register** a `memory/creator_profiles/mark9m_mlbb/` verified profile at this
time. Promotion criteria are unmet. Creating `style_fingerprint.yaml` with
`framework_status: verified_creator_framework` now would write an unverified claim
into the permanent knowledge base — a direct contradiction of the SCOS charter.

The existing `analysis/REF_mark9m_mlbb/` working hypothesis should remain as-is,
clearly tagged **Observed Style (n=1, unvalidated)**.

### To unblock and resume this study
Provide **3–5 additional published mark9m (MLBB) videos**, e.g. drop them in
`input/reference/mark9m/` named `mark9m_02.mp4 … mark9m_06.mp4`. On arrival the
protocol runs end-to-end:

1. Phase 1 — `video_profile.md` per video (duration, fps, AR, BPM, reward interval,
   structure, end card, concealment method, pacing model).
2. Phase 2 — `hidden_cut_matrix.md` via HUD-OCR boundary/kill detection (the method
   that cracked the original) across all videos.
3. Phases 3–5 — reward-interval, BPM, and conversion-system distributions.
4. Phase 6 — `style_drift_report.md` (LOW/MED/HIGH).
5. Phase 7 — `framework_confidence.md` with real cross-video scores.
6. Promotion + memory registration **iff** overall ≥ 85%.

### Provisional falsification targets (to attack once videos exist)
When the corpus arrives, *try to break* — do not confirm — these:
- **H1 (cuts):** find ≥1 mark9m video that is a genuine single match (no concealed
  seams). One clean counterexample weakens "Hidden Match Montage" as an archetype.
- **H2 (9s):** if reward intervals scatter widely (CV high) across videos, "≈9s
  pacing" is an artifact, not a rule.
- **H3 (BPM):** if BPM ranges across genres per video, "80–85 BPM" is coincidence.
- **H4 (end card):** find any video lacking the silent `@handle` card → "standardized
  conversion system" fails.

---

### Provenance
- Workspace inventory + ffprobe characterization performed 2026-06-21.
- No video content was fabricated; all "N/A" entries denote genuinely unmeasurable
  quantities at n=1, not zero values.
- Prior single-video analysis: `analysis/REF_mark9m_mlbb/`.

---

## ADDENDUM A — Corpus update attempt (2026-06-21)

Two files were added to `input/reference/mark9m/`. Both were inspected (md5 + ffprobe
+ frame extraction). **Neither adds a published-edit specimen; verdict unchanged.**

| File | md5 | What it is | Counts toward corpus? |
|---|---|---|---|
| `Download.mp4` | `24dda92f…` | **Byte-identical duplicate** of the original reference | ❌ no (same file) |
| `ac290c8b-…-a888dd7edbef.mp4` | `0a9f028b…` | **Raw single-match MLBB replay capture** — see below | ❌ no (not a published edit; provenance unconfirmed) |

### Forensic read on `ac290…mp4`
- **Game confirmed: Mobile Legends: Bang Bang.** Lord/turtle objective, MLBB HUD,
  hero portrait rails, gold counters, Thai in-game callout text.
- **It is RAW replay-player footage, not an edited upload.** Every sampled frame
  (5s / 150s / 350s / end) shows the MLBB **replay scrubber** at the bottom
  (`⏸ ▬▬ 1X +`) with the match's own timecode (`12:13 / 13:13:46`, `17:55 / 18:46`).
- **One continuous match.** Match timer advances monotonically forward
  (≈12:13 → 17:58); kill score climbs 20→28. No cuts, no music montage.
- **Format:** 640×296 landscape, ~451s (7.5 min), low bitrate (~652 kbps) — a screen
  capture, not a vertical-feed deliverable.
- **No conversion layer.** Final frame is mid-gameplay; **no end card, no silent
  black, no `@handle`.** The video simply stops.
- **Attribution to mark9m UNCONFIRMED.** Visible player tags read `TESSHU_MGN` /
  `TESHKURIN`; no `mark9m` watermark or handle anywhere. Could be source material,
  the user's own replay, or a third party.

### Why it cannot validate the framework
Every pillar of the hypothesis (Curate / Conceal / Pace / Convert) is an
**editing-layer** claim. Raw replay footage has no editing, no concealed seams, no
beat-synced pacing, and no end card — so it cannot confirm or deny any pillar. It is
the *input*, not the *output*.

### What it DOES contribute (one corroboration, not a validation)
It establishes an empirical baseline: **a real single MLBB match runs ~7.5+ min with a
strictly forward-running timer.** This *strengthens* the original within-video
hidden-cut finding by contradiction — the 101s published short, whose timers jumped
*backward* and scores *reset*, therefore cannot be one match and must be a multi-match
splice. Useful corroboration of H1, but still **n=1 on published edits.**

### Verdict (unchanged)
```text
Published-edit corpus: still n=1  →  cross-video consistency: UNDEFINED
mark9m_mlbb : Observed Style  →  Observed Style   (NO CHANGE, promotion DENIED)
```

### Still needed to run the real study
**3–5 PUBLISHED mark9m shorts** (the edited TikTok/Reels uploads — vertical, music,
end card intact), not raw match replays. Drop them in `input/reference/mark9m/`
named `mark9m_02.mp4 …`. The raw replay is welcome to keep as a "master clip" /
source reference, but it occupies the *source* slot, not a *specimen* slot.

*Identification frames retained at `analysis/creator_validation/mark9m/_idframes/`.*
