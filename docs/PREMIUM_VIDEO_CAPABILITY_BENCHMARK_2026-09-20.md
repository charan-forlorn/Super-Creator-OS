# Premium Video Capability Benchmark â€” 2026-09-20

## Benchmark corpus

### Premium branded / commercial films â€” 10
1. The Last Barf Bag â€” Dramamine
2. The Cassette â€” Palliative Care Queensland
3. Jindal - The Steel of India â€” Jindal Steel & Power
4. Considering What? â€” Channel 4
5. Anatomy of a Champion â€” FIGS
6. The Last Observers â€” Patagonia
7. 109Â° Below â€” Arc'teryx
8. Daniel Really Suits You â€” Human Rights Campaign Foundation
9. Eye See â€” Pagani Eyewear
10. The One Under The Sun â€” CeraVe
Source: Vimeo Best Branded Videos 2024.

### Premium branded / editorial / title â€” 10
1. Arctic Alchemy
2. Everybody's Live with John Mulaney | Weekly Promos
3. Feels
4. The Final Copy Of Ilon Specht
5. Tháº¿ Giá»›i
6. Haqqim Bor
7. New Jeans
8. No Project Without Drama
9. Severance â€“ Opening Title Sequence (Season 2)
10. Some Interesting Apples
Source: Vimeo Best of the Year 2025.

### TikTok-first short-form / performance / creator-native â€” 10
1. TUI â€” Happy Bag
2. Reading & Leeds Festival
3. Bloo â€” This or That / Loo Thoughts
4. Pedigree â€” Adopt, Don't Shop
5. Vaseline â€” Vaseline Verified
6. Pracuj.pl
7. Konesso
8. Knorr â€” Szama 24/7
9. BCR
10. Plush
Observed patterns: creator-style framing, TikTok-native editing, green-screen/split-screen, Spark Ads, rapid creative iteration, community participation, measurable performance.

### Premium motion design / 2D / 3D / product visualization â€” 10
1. Melio - Accounting is Changinging
2. Simplex - Now I'm a Decision
3. NOBJECTS by CLIM
4. At your door â€” 2D & 3D motion
5. Graphika Manila 2025 Open Titles
6. THREE CENTS â€” A STORY BEHIND BARS
7. Sarbast new bottle design
8. MIRAGE
9. Optious 2025 Brand Video
10. Crumb Studio Rebrand
Observed patterns: product lighting/reflections, 2D/3D animation, simulation, compositing/grading, camera language, title animation, sound design.

### Premium product / developer / enterprise presentation â€” 10
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

### Premium short / music / experimental editorial â€” 10
1. A Bear Remembers
2. A Kind of Testament
3. Beyond Failure
4. Chico
5. Christmas, Every Day
6. Dissolution
7. La Perra
8. Talking Heads â€” Psycho Killer
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

R1 Premium Motion Grammar â€” DONE
R2 Compositing & transition runtime â€” masks, blend modes, glow/blur/vignette, slide/zoom/whip/dip transitions, per-layer animation
R3 Audio-reactive editorial â€” real beat/energy analysis, beat-aligned shot markers, transient/SFX timing
R4 Premium typography â€” kinetic captions, word-level highlighting, emphasis styles
R5 Look development â€” LUT/color transform contract, grade presets, material/light/shadow language
R6 2.5D / 3D / product scenes â€” depth camera, parallax, product lighting and bounded 3D scenes
R7 Evidence-backed shot intelligence â€” storyboard to shot graph, asset-to-shot matching, style profile to motion grammar, telemetry to observed evaluation
R8 Premium benchmark harness â€” repeatable render/evaluation of briefs across grammar profiles with evidence and cost tracking


## R2-R8 implementation status

R2 â€” Compositing / transitions: source alpha/luma masks, global blur/glow/color-mix, browser-compatible blend mapping, and canonical Remotion pixel runtime verified.
R3 â€” Audio-reactive editorial: real-byte RMS/onset analysis, deterministic BPM estimation, beat events, and renderer beat-pulse binding verified.
R4 â€” Premium typography: word-level runtime rendering verified.
R5 â€” Look development: actual FFmpeg finishing path + cache identity verified.
R6 â€” True 3D runtime: Three.js WebGL + GLTFLoader is active inside the canonical Remotion composition; real GLTF pixel render verified.
R7 â€” deterministic storyboard planner + conversion into canonical PremiumMotionGraph verified.
R8 â€” repeatable benchmark harness + 60-reference benchmark dossier verified.

The system deliberately distinguishes capability-contract verification from pixel/render verification and from real production telemetry. No performance outcome is inferred from the benchmark corpus.


## R9 â€” AI Video Director / Provider Routing â€” 2026-09-20

Competitive architecture analysis was performed against a current strategic reference set of 10 AI video platforms, with public product/API documentation and open-source implementations used where available. The analysis found that the biggest architectural differentiator is not a single generation model but a director layer around models: multimodal references, shot-level controls, capability-aware routing, asynchronous generation tasks, continuity, artifact sealing, and final render integration.

SCOS now implements the deterministic orchestration contract for that layer:
- ReferenceAsset and continuity keys
- ProviderProfile / ProviderRegistry capability routing
- ShotGenerationSpec
- GenerationPlan with fingerprint
- director-prompt compilation
- storyboard -> generation plan compiler
- GenerationTask async lifecycle with retry/cancel/fail-closed transitions
- GenerationArtifact validation
- GenerationPlan roundtrip into ProductionGraph

The router includes capability profiles for current Veo, Seedance, Runway, Kling, Luma, Firefly, Hailuo, Pika, Grok, and HeyGen production lanes. These are capability contracts, not claims that live provider API credentials are configured.

## R10 â€” Provider Execution Plane

R9 established deterministic director/provider routing. R10 adds the execution plane needed to turn those decisions into governed production work: concrete provider adapters, execution-time contract validation, reference byte sealing, async task reconciliation, artifact/evidence sealing, continuity QC, bounded fallback, and a renderer-facing generated-clip manifest.

The implementation intentionally keeps the existing ProductionGraph and Remotion renderer as the canonical downstream system. It does not create a second render/orchestration graph.

R10 verification on 2026-09-20:
- Runtime tests: 8 passed.
- Premium Media suite: 51 passed.
- Full SCOS regression was not yet resealed at the time of this section; final commit evidence must use the latest full-suite run.
- No live provider execution is claimed because the machine has no configured top-three provider credentials.

## R10 Final Verification Seal — 2026-09-20

- Runtime execution suite: **8 passed**.
- Premium Media suite: **51 passed**.
- Full SCOS regression: **3037 passed, 21 skipped, 21 deselected** in **211.01s**.
- Provider credentials: none configured; live vendor execution remains unclaimed.

## Final R11-R15 Regression Seal — 2026-09-20

- Full SCOS regression: 3045 passed, 21 skipped, 21 deselected in 193.53s.
- python -m compileall -q scos: PASS.
- Premium Media suite: 59 passed.
- R11 Remotion pixel smoke: 180/180 frames, 1080x1920, 30 fps, 6.000 s, H.264.
- R11 generated-clip assembly SHA-256: e20cb3da7d73988c9d5df3d3026f444875539425d77bf797383299f69f5c6028.
- Provider credentials remain unconfigured: GEMINI_API_KEY=False, LAS_API_KEY=False, RUNWAYML_API_SECRET=False.
- No live/paid provider generation was triggered.
- Human Publish Gate: NOT_APPROVED.
- External Publish: NOT_PERFORMED.
