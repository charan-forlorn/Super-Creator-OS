# Memory Schema — v2 Extension (video-use engine)

> ADDITIVE. Does not change `schema.md` or `database.json`. All fields below are
> **OPTIONAL**. Old records without them stay 100% valid; the Orchestrator reads
> them with `.get(field, default)`. Only populate them when the video-use engine
> was actually used in a session.

## New optional fields (append inside the existing record object)

These are written automatically by `integrations/adapter/render_to_memory.py`
(the "return adapter") after a render completes.

```json
{
  "engine": "video-use",                    // or "native-ffmpeg" (default if absent)
  "clip_type": "gaming_moba",               // gaming_moba | talking_head | interview | image_montage
  "transcribed": true,                      // true if ElevenLabs Scribe was used
  "edl_path": "work/edit/edl.json",         // path to the EDL that produced final.mp4
  "grade_used": "warm_cinematic",           // preset name or raw ffmpeg filter
  "subtitle_style": "transcript-derived (bold-overlay, 2-word UPPERCASE)",
  "cut_padding_ms": [50, 80],               // [pre, post] working window actually used
  "render_success": true,                   // duration of output matched the EDL
  "qa_pass": null,                          // true/false from qa-reviewer, or null if not run
  "highlight_anchors": [                     // transcript timestamps that mark a beat
    {"t": 69.56, "label": "Double kill.", "kind": "callout"},
    {"t": 19.50, "label": "(game sounds)", "kind": "audio_event"}
  ],
  "retention_signals": {                     // derived signals to inform next retention_score
    "num_segments": 3,
    "avg_segment_s": 4.53,
    "kept_speech_s": 13.58,
    "source_total_s": 71.79,
    "kept_ratio_pct": 19,
    "output_duration_s": 24.27,
    "has_cold_open": true
  },
  "render_specs": {                          // engine render facts, for next-time reuse
    "resolution": "1080x1920@30fps",
    "fps": 30,
    "output_duration_s": 24.27
  }
}
```

`highlight_anchors` is especially valuable for the **gaming** niche: it stores the
exact word-timestamps of in-game kill callouts ("Double kill", "Triple kill"),
which the next near-niche project reuses to find the cold-open hook instantly
instead of re-scanning RMS peaks.

## Backward-compatibility rule

- A record may have **none, some, or all** of these. Treat every v2 field as
  `optional`. The canonical v1 fields in `schema.md` remain required and unchanged.
- The Orchestrator's STEP 15 Append still writes one record per project. v2 fields
  are merged into that same object — no second array, no schema migration.

## Why these fields

`editing_specs` (v1) is a free-text string. These structured fields let the
`video-editor` skill REUSE a proven EDL shape (grade + padding + resolution) for a
near-niche project instead of re-deriving it, which is the whole point of the
memory loop. They complement `editing_specs`, they don't replace it.
