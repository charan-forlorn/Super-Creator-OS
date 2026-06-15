# Memory Schema — v2 Extension (video-use engine)

> ADDITIVE. Does not change `schema.md` or `database.json`. All fields below are
> **OPTIONAL**. Old records without them stay 100% valid; the Orchestrator reads
> them with `.get(field, default)`. Only populate them when the video-use engine
> was actually used in a session.

## New optional fields (append inside the existing record object)

```json
{
  "engine": "video-use",                    // or "native-ffmpeg" (default if absent)
  "transcribed": false,                     // true if ElevenLabs Scribe was used
  "edl_path": "work/edit/edl.json",         // path to the EDL that produced final.mp4
  "grade_used": "warm_cinematic",           // preset name or raw ffmpeg filter
  "subtitle_source": "on-screen-text",      // "on-screen-text" (adapter SRT) | "transcript" | "none"
  "cut_padding_ms": [50, 80],               // [pre, post] working window actually used
  "render_specs": {                         // engine render facts, for next-time reuse
    "resolution": "1080x1920",
    "fps": 30,
    "self_eval_passes": 1
  }
}
```

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
