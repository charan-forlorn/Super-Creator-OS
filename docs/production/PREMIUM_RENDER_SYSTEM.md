# SCOS Premium Render System R1

## Goal
Turn SCOS into a reusable premium video-production subsystem, not a one-off renderer.
The default creative shape is one screen. The reference supplied for this work was analyzed as a
two-panel demo; only its lower Result surface is used as the visual-structure starting point.

## Architecture

```
Brief
  -> Composition Plan (one-screen)
  -> Rights-aware Asset Registry
  -> Voice / Music / SFX / Ambience stems
  -> Subtitle Cues
  -> Production Graph
       - Creative / Scene
       - Asset / Rights
       - Audio / Caption
       - Brand / Style references
       - learning loop identity (loop_run_id when supplied; never fabricated)
  -> Platform-neutral Master Render
       - Remotion motion / UI / typography
       - FFmpeg finishing
       - stem mix / ducking / compression
       - loudness normalization / true-peak ceiling
       - subtitle burn-in when requested
  -> HVS-aligned QC
       - geometry / fps / duration
       - black-frame / frozen-frame advisory
       - audio clipping / near-silence
       - loudness / subtitles
  -> Render Cache / Incremental Reuse
       - Remotion stage keyed by composition + props + source-tree fingerprint + render profile
       - final master keyed by input SHA + audio/captions + render profile + FFmpeg identity
       - platform delivery keyed by master SHA + destination profile + resolved encoder + FFmpeg identity
       - every cache hit re-materializes from a checksum-sealed artifact and re-runs current QC
  -> Hardware-aware Finishing
       - local NVENC capability detection
       - CPU/GPU policy is explicit per render profile
       - GPU is used for compatible social/ad finishing and delivery when available
       - master profiles can remain CPU-bound for stable archival output
  -> Platform Delivery Render
       - destination-specific geometry / duration / bitrate / file-size rules
       - delivery provenance linking back to master SHA-256
       - delivery rendering reuses the shared cache and hardware policy; no parallel delivery subsystem
  -> Provenance + Learning Handoff
       - graph fingerprint
       - master + delivery checksums
       - observed telemetry remains NOT_OBSERVED until real telemetry exists
  -> Human Publish Gate (manual)
```

## Renderer strategy
Remotion is the primary renderer for animated UI, typography, interface mockups, timing-driven motion,
and deterministic React compositions. FFmpeg remains the finishing engine. The legacy video-use backend
is retained for EDL-compatible production and is not duplicated.

## Incremental rendering and hardware policy

Derived render artifacts are stored in the ignored local render cache. Cache keys include the bytes and
configuration that materially affect the stage, rather than only an output filename. Cache hits are never
blindly trusted: the artifact checksum is verified, the artifact is materialized atomically, and the
current QC contract is re-applied.

Hardware selection is capability-driven rather than host-name-driven. render_acceleration may be
cpu, auto, or gpu. auto uses NVENC when the local FFmpeg build exposes it; gpu fails closed when
NVENC is unavailable. CPU-bound master profiles remain available for stable archival output, while
social/ad finishing and destination delivery may use NVENC to reduce render latency.

## Brand, asset index, and creative variants

Brand Kit is resolved from the authoritative Control Center store at the canonical render boundary. Brand
colors, fonts, display name, CTA label, and fingerprint are compiled into the Remotion props. Caption
typography and the safe footer are brand-aware. Logo references remain provenance data until the asset
registry can resolve a real local logo file; no synthetic logo substitute is generated.

Local asset indexing operates through the existing AssetRegistry rather than a second asset database.
The indexer is incremental, checksum-based, understands audio/video/image/font media types, consumes
optional rights sidecars, preserves explicit rights evidence, and never downloads from a source.
Remote acquisition remains a separate explicit operator-controlled step.

Creative variants are generated from the same ProductionGraph. A bounded variant spec can override
creative scene fields without changing scene timing or rights boundaries. Each variant receives a
stable variant_id that becomes part of the graph fingerprint and naturally separates cache entries.
Variant generation creates artifacts only; no performance winner is inferred.

## Audio strategy
The source timeline stores voice, music, SFX, and ambience independently. The final mix uses voice
as the anchor and sidechain-ducks music while speech is present. The finish stage targets -16 LUFS
and a -1 dBTP ceiling in the default profile. These are engineering defaults, not universal guarantees
for every ad platform; platform-specific delivery requirements must be configured per destination.

FFmpeg's loudnorm filter supports EBU R128 loudness normalization and true-peak control. Use it after
the mix rather than repeatedly normalizing individual stems.

## Captions
SRT is accepted as a portable interchange. ASS is generated for the FFmpeg/libass burn-in path.
Remotion's caption tooling is the preferred path when captions need kinetic per-word animation. Caption
cues are validated for ordering, overlap, and duration before export.

## Voices
Thai and English are first-class. Provider selection is explicit:
- local Piper for low-cost/private execution where a licensed voice model exists;
- Chatterbox for its advertised multilingual languages (Thai is not in its general language list);
- Google Cloud Chirp3-HD for premium Thai when the project explicitly enables paid cloud use;
- existing ElevenLabs Scribe for word-level transcription when its configured key is available.

The system does not silently switch to a cloud provider or invent a voice license.

## Music and SFX
Catalogs are separated by legal scope. Mixkit and Pixabay are useful commercial-content sources, but
the license for the specific asset is still recorded. Freesound CC0/CC-BY can be used when attribution
and provenance are captured. YouTube Audio Library is treated as platform-scoped by default. Popular
Thai/international songs are ingested only with explicit rights evidence.

## Ad-capable output
An ad profile requires:
1. every audio/visual asset to pass rights validation;
2. commercial use to be explicitly cleared;
3. platform scope/territory/term evidence where applicable;
4. voice and music stems separated until final mix;
5. captions validated;
6. final file machine-QC'd;
7. provenance manifest written;
8. Human Publish Gate still remains manual.

## Quality hierarchy
1. Source truth and creative brief
2. Rights and asset provenance
3. Narrative pacing
4. Visual polish and motion
5. Voice intelligibility
6. Music/SFX integration
7. Subtitle legibility
8. Final technical compliance
