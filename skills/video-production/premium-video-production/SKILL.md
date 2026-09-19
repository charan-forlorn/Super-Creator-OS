# Premium Video Production Skill

## Mission
Produce high-value single-screen vertical video with deterministic rendering, rights-aware media,
professional typography, bilingual Thai/English voice, subtitles, sound design, music, and machine QA.

## Default operating model
- Single-screen composition is the default. The reference's lower Result surface is the structural starting point.
- Prefer Remotion for motion graphics, UI, typography, timing, and deterministic animation.
- Prefer FFmpeg for finishing, loudness, muxing, subtitle burn-in, and media transforms.
- Reuse the existing video-use backend for legacy EDL workflows; do not duplicate it.
- Local/free-first. Paid cloud TTS or music is opt-in and never an automatic fallback.
- Fail closed on missing rights, missing assets, invalid timing, failed probes, or failed QA.
- Human Publish Gate remains Human-controlled and must never be inferred.

## Production lanes
1. Brief/Goal → narrative and one-screen composition plan.
2. Asset intake → local media + explicit provenance/rights.
3. Voice → Thai/English provider selection, then loudness/clarity finishing.
4. Music/SFX → rights-checked catalog, stem-separated mix.
5. Captions → SRT/word timing → deterministic ASS/Remotion captions.
6. Render → Remotion composition at target profile.
7. Finish → FFmpeg audio ducking, loudness, true-peak ceiling, subtitle burn-in.
8. QA → ffprobe + loudness + subtitle integrity + optional perceptual comparison.
9. Evidence → checksum, provenance, licenses, render profile, tool versions.

## Rights policy
Popular commercial songs are never copied from streaming/video platforms merely because they are
publicly accessible. A real song is eligible only when a license record covers the actual intended use,
platform, territory, term, and advertising scope. Unknown or non-commercial assets are blocked.

## Voice policy
- Thai premium path: configured Google Cloud Chirp3-HD or a specifically licensed Thai local voice.
- Thai local path: Piper 1.8+ Thai phonemizer/voice when a model with acceptable license is installed.
- English/multilingual local path: Chatterbox where its supported language list and output constraints fit.
- Existing ElevenLabs Scribe remains the reusable transcription lane.
- Never silently substitute a language/model that is not supported.

## Audio policy
Maintain independent voice/music/SFX/ambience stems until final mix. Voice is the anchor; music is ducked
during speech; final output is normalized and true-peak limited. Use 48 kHz stereo for premium output.

## Subtitle policy
Validate monotonic cue timing and media bounds. For FFmpeg, compile to ASS and use libass. For Remotion,
prefer @remotion/captions. Support Thai and English text without assuming Latin-only wrapping.

## Evidence
Every final render keeps a provenance JSON with output SHA-256, source SHA-256, profile, audio stems,
subtitle count, and publish gate state. No external publish is performed by this skill.


## Canonical architecture boundaries
- Premium Media must enter SCOS through the canonical `scos.render.RenderBackend` contract; do not create a second orchestration/render contract.
- Build creative work as a deterministic `ProductionGraph` containing brief, scenes, assets, audio, captions, brand/style references, master profile, delivery profiles, and `loop_run_id` when supplied.
- `Master Render` is platform-neutral production output. `Platform Delivery Render` is a separate destination transformation and validation step.
- Brand Kit is read-only authoritative project state from the Control Center local store. If an explicit `brand_kit_id` is requested and cannot be resolved, fail closed; never synthesize a substitute brand.
- Safe-zone validation reuses the HVS inner-90% baseline as a layout-integrity gate. It is not a claim of vendor-specific UI certification until evidence-backed platform overlays exist.
- Asset intelligence is local-first: rank already-registered assets deterministically by media type, tags, language, duration, sealed checksum, and explicit rights. Acquisition remains a separate explicit step.
- Learning provenance must carry graph fingerprint, artifact checksum, and `loop_run_id` when present. Real performance telemetry remains `NOT_OBSERVED` until observed data is actually joined.
