# Premium Video Capability Benchmark — 2026-09-20

## Benchmark corpus

### Premium branded / commercial films — 10
1. The Last Barf Bag — Dramamine
2. The Cassette — Palliative Care Queensland
3. Jindal - The Steel of India — Jindal Steel & Power
4. Considering What? — Channel 4
5. Anatomy of a Champion — FIGS
6. The Last Observers — Patagonia
7. 109° Below — Arc'teryx
8. Daniel Really Suits You — Human Rights Campaign Foundation
9. Eye See — Pagani Eyewear
10. The One Under The Sun — CeraVe
Source: Vimeo Best Branded Videos 2024.

### Premium branded / editorial / title — 10
1. Arctic Alchemy
2. Everybody's Live with John Mulaney | Weekly Promos
3. Feels
4. The Final Copy Of Ilon Specht
5. Thế Giới
6. Haqqim Bor
7. New Jeans
8. No Project Without Drama
9. Severance – Opening Title Sequence (Season 2)
10. Some Interesting Apples
Source: Vimeo Best of the Year 2025.

### TikTok-first short-form / performance / creator-native — 10
1. TUI — Happy Bag
2. Reading & Leeds Festival
3. Bloo — This or That / Loo Thoughts
4. Pedigree — Adopt, Don't Shop
5. Vaseline — Vaseline Verified
6. Pracuj.pl
7. Konesso
8. Knorr — Szama 24/7
9. BCR
10. Plush
Observed patterns: creator-style framing, TikTok-native editing, green-screen/split-screen, Spark Ads, rapid creative iteration, community participation, measurable performance.

### Premium motion design / 2D / 3D / product visualization — 10
1. Melio - Accounting is Changinging
2. Simplex - Now I'm a Decision
3. NOBJECTS by CLIM
4. At your door — 2D & 3D motion
5. Graphika Manila 2025 Open Titles
6. THREE CENTS — A STORY BEHIND BARS
7. Sarbast new bottle design
8. MIRAGE
9. Optious 2025 Brand Video
10. Crumb Studio Rebrand
Observed patterns: product lighting/reflections, 2D/3D animation, simulation, compositing/grading, camera language, title animation, sound design.

### Premium product / developer / enterprise presentation — 10
1. Apple WWDC25 Keynote
2. Google I/O 2025 Keynote
3. Microsoft Build 2025 Opening Keynote
4. Figma Config 2025 Keynote
5. AWS re:Invent 2025 Keynote
6. OpenAI DevDay 2025 Opening Keynote
7. Salesforce Dreamforce 2025 Main Keynote
8. NVIDIA GTC Washington 2025 Keynote
9. Adobe MAX 2025 Opening Keynote
10. Samsung Galaxy Unpacked Summer 2025
Observed patterns: chaptering, live/demo footage, motion graphics, UI capture, typography, stage/LED compositing, speaker identity cards, product closeups, repeated visual language.

### Premium short / music / experimental editorial — 10
1. A Bear Remembers
2. A Kind of Testament
3. Beyond Failure
4. Chico
5. Christmas, Every Day
6. Dissolution
7. La Perra
8. Talking Heads — Psycho Killer
9. We Were the Scenery
10. 27
Source: Vimeo Best Videos 2025.

## Capability extraction

- one clear idea per shot/beat
- explicit hook / setup / escalation / payoff
- multiple visual layers rather than one flat scene
- camera movement separated from object movement
- keyframe-based motion with easing
- deliberate transitions rather than arbitrary effects
- controlled typography hierarchy
- compositing: masks, blend modes, overlays, glows, depth, light
- color/finish as a coherent visual system
- audio hierarchy: voice/music/SFX/ambience plus ducking and timing
- captions treated as animated design
- product/UI/screen capture integrated into narrative
- 2D/3D and photographic material mixed coherently
- platform-specific shot rhythm and safe zones
- reusable visual grammar/style profiles
- QC/provenance/telemetry preserved through the whole render path

## Current SCOS capability

Strong: ProductionGraph fingerprinting, Remotion/FFmpeg routing, render cache, CPU/auto/GPU routing, NVENC, Brand Kit, local rights-aware asset indexing, layered audio, subtitles, delivery profiles, safe-zone baseline, fail-closed QC, creative variants, provenance, telemetry binding foundation.

Material gaps: first-class shot grammar, keyframes, easing, camera motion, 2.5D/depth, broad transition library, masks/blend modes, advanced effect stack, LUT/color-grade contract, time-remap/speed curves, beat/energy mapping, word-level animated captions, advanced typography, 3D/product scenes, platform-specific safe-zone profiles, explicit storyboard/shot-plan contract.

## Architecture decision

Do not add isolated effects one by one. The high-leverage abstraction is:

ProductionGraph -> PremiumMotionGraph -> existing Remotion props -> existing render cache -> existing QC -> existing provenance -> existing telemetry

PremiumMotionGraph becomes the first-class contract for shot/layer/keyframe/transition/camera/effect grammar without creating a second orchestration system.

## Implemented R1

Added scos/premium_media/motion.py with:
- Keyframe and AnimatedNumber
- Transform2D
- Camera2D
- EffectStack
- MotionLayer
- ShotTransition
- PremiumShot
- PremiumMotionGraph
- deterministic fingerprinting
- fail-closed validation
- serialization into existing Remotion props

ProductionGraph now carries motion_graph and includes it in its graph fingerprint, preserving cache/provenance identity.

## Development order

R1 Premium Motion Grammar — DONE
R2 Compositing & transition runtime — masks, blend modes, glow/blur/vignette, slide/zoom/whip/dip transitions, per-layer animation
R3 Audio-reactive editorial — real beat/energy analysis, beat-aligned shot markers, transient/SFX timing
R4 Premium typography — kinetic captions, word-level highlighting, emphasis styles
R5 Look development — LUT/color transform contract, grade presets, material/light/shadow language
R6 2.5D / 3D / product scenes — depth camera, parallax, product lighting and bounded 3D scenes
R7 Evidence-backed shot intelligence — storyboard to shot graph, asset-to-shot matching, style profile to motion grammar, telemetry to observed evaluation
R8 Premium benchmark harness — repeatable render/evaluation of briefs across grammar profiles with evidence and cost tracking


## R2-R8 implementation status

R2 — Compositing / transitions: contract + canonical Remotion pixel runtime verified.
R3 — Audio-reactive editorial: real-byte analysis + renderer energy-event binding verified.
R4 — Premium typography: word-level runtime rendering verified.
R5 — Look development: actual FFmpeg finishing path + cache identity verified.
R6 — 2.5D depth runtime verified; 3D remains a bounded adapter contract, not a claim of full 3D asset rendering.
R7 — deterministic storyboard planner + conversion into canonical PremiumMotionGraph verified.
R8 — repeatable benchmark harness + 60-reference benchmark dossier verified.

The system deliberately distinguishes capability-contract verification from pixel/render verification and from real production telemetry. No performance outcome is inferred from the benchmark corpus.
