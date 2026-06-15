# Video Editor — Engine Bridge (video-use)

> ADDITIVE companion to `SKILL.md`. Does not change the skill's contract. Use this
> when a project benefits from the video-use production engine (real footage with
> speech, precise cuts, correct render/grade/subtitle pipeline). For image-montage
> or RMS-peak gaming edits, the native Super Creator OS path still applies.

## When to route to the engine

| Material | Path |
|----------|------|
| Talking head / interview / review / tutorial (has speech) | **video-use engine** (transcribe → cut on word boundaries) |
| Real video footage, precise cuts, burn subtitles, color grade | **video-use engine** (`render.py` + `grade.py`) |
| Still-image montage (screenshots, generated images) | **Super Creator OS native** (asset-assembly + Ken Burns) |
| Gaming highlight via RMS-peak detection (e.g. MOBA) | **Super Creator OS native** (keep RMS workflow) |

## How to call it (from project root)

1. After producing `timeline_format.md` (skill STEP 3 "Build Timeline"), convert it:
   ```bash
   python integrations/adapter/timeline_to_edl.py <timeline.md> \
       --assets-dir <assets_dir> -o work/edit/edl.json --grade <preset|none>
   ```
   The adapter also writes `from_timeline.srt` (burn-ready captions built from the
   on-screen `Text:` fields — no ElevenLabs needed for text overlays).

2. Render:
   ```bash
   python integrations/video-use/vu.py render work/edit/edl.json -o work/edit/preview.mp4 --preview
   ```

3. Self-eval (the engine's discipline — adopt it for QA, see ENGINE_SKILL.md Hard Rules):
   ```bash
   python integrations/video-use/vu.py timeline_view work/edit/preview.mp4 <t0> <t1>
   ```

## The 12 Hard Rules (from `integrations/video-use/engine/ENGINE_SKILL.md`)

Adopt these as non-negotiable render-correctness rules — they prevent silent
failures the native path has hit before (audio pops, hidden subtitles):

1. Subtitles applied LAST in the filter chain (after overlays).
2. Per-segment extract → lossless `-c copy` concat (not single-pass filtergraph).
3. 30ms audio fades at every segment boundary (kills cut pops).
4. Overlays use `setpts=PTS-STARTPTS+T/TB`.
5. Master SRT uses output-timeline offsets.
6. Never cut inside a word (snap to transcript word boundary).
7. Pad every cut edge (30–200ms working window).
8. Word-level verbatim ASR only (never phrase/SRT mode).
9. Cache transcripts per source.
10. Parallel sub-agents for multiple animations.
11. Strategy confirmation before execution.
12. All session outputs under the edit dir — never inside `integrations/`.

## Return contract (unchanged)

Still return `editing_specs` to the Orchestrator as before. Optionally also return
the structured v2 fields in `memory/schema_v2_extension.md` (grade_used,
cut_padding_ms, render_specs) so the next near-niche project can reuse them.
