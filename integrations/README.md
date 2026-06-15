# integrations/ — video-use engine bridge

Isolation layer that plugs the **video-use** production engine (Browser Use, MIT)
into **Super Creator OS** without modifying any core file. Super Creator OS stays
the brain (strategy, story, retention, memory, captions); video-use becomes the
hands (word-level transcription, correct render pipeline, auto color grade).

## Layout

```
integrations/
├── README.md                     ← this file
├── video-use/
│   ├── vu.py                     ← Windows-safe launcher (forces UTF-8) — USE THIS
│   ├── .env.example              ← ELEVENLABS_API_KEY=
│   └── engine/                   ← vendored video-use (UNMODIFIED except 2 win-compat patches)
│       ├── helpers/*.py          ← transcribe / pack / timeline_view / render / grade
│       ├── manim-video/          ← optional animation sub-skill
│       ├── ENGINE_SKILL.md       ← original video-use SKILL.md (full craft + 12 hard rules)
│       └── LICENSE               ← MIT (Browser Use)
└── adapter/
    └── timeline_to_edl.py        ← bridge: Super Creator OS timeline_format.md → video-use edl.json (+SRT)
```

## How the two systems connect

```
Super Creator OS workflow (workflow-map.md)
  STEP 6  Video Editor   → produces timeline_format.md
  STEP 12 Render             │
                             ▼
        adapter/timeline_to_edl.py   (timeline_format.md → edl.json + from_timeline.srt)
                             │
                             ▼
        video-use/vu.py render <edl.json> -o final.mp4
  STEP 11 QA Reviewer    → video-use/vu.py timeline_view <out> <t0> <t1>  (visual cut check)
```

## Quick commands (run from project root)

```bash
# Convert a Super Creator OS timeline into a video-use EDL + burn-ready SRT
python integrations/adapter/timeline_to_edl.py \
    source/super_creator_blueprints/timeline_format.md \
    --assets-dir input/frames -o work/edit/edl.json --grade warm_cinematic

# Render (preview is 720p fast; drop --preview for full res)
python integrations/video-use/vu.py render work/edit/edl.json -o work/edit/preview.mp4 --preview

# Auto color-grade analysis of any clip
python integrations/video-use/vu.py grade --analyze <clip.mp4>

# Visual cut-boundary check for QA (filmstrip + waveform PNG)
python integrations/video-use/vu.py timeline_view <video> <start> <end>

# Transcription (needs ELEVENLABS_API_KEY in integrations/video-use/.env)
python integrations/video-use/vu.py transcribe_batch <videos_dir>
```

> Always call helpers through **`vu.py`**, not directly — it forces UTF-8 so the
> engine's Unicode output doesn't crash the Windows console.

## Windows-compat patches applied to the vendored engine

The engine is otherwise byte-for-byte upstream. Two minimal, commented patches
make it run on Windows (both marked `[super-creator-os integration]`):

1. `engine/helpers/grade.py` — `metadata=print:file=` now writes a **relative**
   temp filename in the cwd. ffmpeg's filtergraph cannot parse an absolute
   Windows path (the `C:\` drive colon is read as an option separator and no
   escaping fixes it).
2. `engine/helpers/render.py` — the `subtitles=` filter path now also converts
   backslashes to forward slashes (upstream only escaped the colon).

## Dependencies

- **Working today:** `requests`, `numpy`, `pillow`, `ffmpeg`, `ffprobe` (verified).
- **Needed for `timeline_view.py` only:** `librosa`, `matplotlib` — install with
  `uv pip install librosa matplotlib` (or `pip install`). Not required for
  render / grade / adapter.
- **Needed for transcription only:** an ElevenLabs API key (paid). Copy
  `video-use/.env.example` → `video-use/.env` and fill `ELEVENLABS_API_KEY`.
- **Manim slot only:** `manim` (`uv pip install manim`).

## What does NOT cross the bridge automatically

- **Image-only timelines.** video-use cuts from *video* sources. Still-image
  montage blocks are flagged by the adapter (`_asset_type: image`) and must be
  pre-converted to clips, OR kept on the Super Creator OS native asset-assembly
  path. See the adapter's printed recipe.
- **Transcript-driven cutting** only adds value when sources have **speech**.
  RMS-peak highlight detection (the MOBA path) stays in Super Creator OS.

## Provenance / license

`engine/` is vendored from https://github.com/browser-use/video-use (MIT,
© 2026 Browser Use). License retained at `engine/LICENSE`. Super Creator OS code
and memory remain yours and untouched.
