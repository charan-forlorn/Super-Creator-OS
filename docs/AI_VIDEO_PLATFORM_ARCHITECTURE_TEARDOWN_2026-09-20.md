# AI Video Platform Architecture Teardown + SCOS Upgrade â€” 2026-09-20

## Scope

This benchmark uses public product documentation, public APIs, and public/open-source repositories. Proprietary backend source code for closed platforms is not publicly inspectable, so the analysis reconstructs their production architecture from observable interfaces, documented workflows, API contracts, and open-source implementations rather than claiming access to hidden vendor code.

The goal is not to copy any vendor implementation. The goal is to extract reusable architecture patterns that raise SCOS from a renderer with premium motion capabilities into a model-agnostic AI video production system.

## Current strategic Top-10 reference set

There is no single authoritative global ranking for "best AI video platform"; public usage, benchmark scores, and product breadth measure different things. Current AI Gateway usage data for the last three months shows Seedance, Grok, Veo, MiniMax, Kling, and Wan among the most-used video models, while 2026 creator/industry comparisons consistently include Runway, Luma, Pika, Hailuo, and Adobe Firefly in the leading commercial set.

The resulting Top-10 strategic reference set for SCOS is:

1. ByteDance Seedance / Dreamina / Doubao
2. Google Veo / Flow
3. Runway
4. Kling
5. Luma Dream Machine
6. xAI Grok Imagine Video
7. MiniMax Hailuo
8. Adobe Firefly Video
9. Alibaba Wan
10. Pika

Sora is intentionally not treated as a current platform target: OpenAI states that the Sora web/app product was discontinued on April 26, 2026 and the Sora API is scheduled for September 24, 2026.

## AI-video Top-3 architecture references

### 1. Seedance 2.0

Why it is strategically important:
- Unified multimodal audio-video generation.
- Text + image + audio + video references in a single workflow.
- Up to 9 images, 3 videos, and 3 audio clips can be referenced together.
- References can encode composition, motion, camera movement, effects, and sound.
- Supports controllable extension/editing and 15-second multi-shot audio-video output.

Architecture pattern extracted:
Input reference pack -> multimodal conditioning -> shot/multi-shot generation -> synchronized audio-video artifact.

SCOS adaptation:
ReferencePack + shot-level ShotGenerationSpec + provider routing + asynchronous generation task + final render graph.

### 2. Google Veo 3.1 / Flow

Why it is strategically important:
- Native audio generation.
- Scene, character, object, and style references.
- Camera controls.
- Scene extension.
- First/last frame control.
- Object insertion/removal and outpainting.
- 1080p and 4K outputs.

Architecture pattern extracted:
Director controls are first-class structured inputs around the generation model rather than being encoded only in a free-form prompt.

SCOS adaptation:
Structured camera/motion/style/reference fields are compiled into provider prompts and capability requirements; final clips are normalized into the canonical ProductionGraph.

### 3. Runway Gen-4.5

Why it is strategically important:
- Explicit asynchronous task API.
- Image-to-video and text-to-video are exposed as tasks.
- Task output is polled/waited and errors are typed.
- Public docs provide recipes for product ads, product swaps, UGC, and multi-shot workflows.
- Reference media is a first-class API concept.

Architecture pattern extracted:
Create task -> receive task ID -> poll/wait -> validate task outcome -> obtain artifact -> continue production pipeline.

SCOS adaptation:
GenerationTask state machine with terminal artifact requirements, retry transitions, provider task IDs, and deterministic artifact metadata.

## Top-3 rendering architecture references

### 1. Adobe After Effects / aerender

After Effects exposes a command-line aerender executable, frame-range rendering, composition selection, reusable running instances, multi-frame rendering, and multi-machine/render-farm workflows.

Pattern extracted:
Render job -> deterministic project/comp/input set -> frame range -> render engine -> progress/logging -> artifact.

### 2. DaVinci Resolve

Resolve uses an explicit Render Queue and supports scripting triggers before/after rendering.

Pattern extracted:
Render jobs are durable objects that can be queued, edited, restarted, and scripted around.

### 3. Remotion

Remotion exposes code-first composition, parameterization, batch rendering, server-side rendering, concurrency, cancellation, progress callbacks, reused render servers, frame-range rendering, parallel encoding, and artifact callbacks.

Pattern extracted:
Source-of-truth code + serialized props -> reusable render server/browser -> frame work -> parallel encoding -> final artifact.

SCOS already uses this architecture and has now pushed it further with production graph fingerprinting, cache, QC, and provenance.

## 3D reference

Blender remains an important 3D benchmark for SCOS R6 because it separates scene description, camera, geometry, materials, and headless rendering. SCOS currently uses Three.js/GLTF inside Remotion for the bounded in-composition 3D path.

## Open-source model architecture patterns

### HunyuanVideo

The public implementation shows a clean separation between:
- argument/config parsing
- model loading
- sampler/inference
- seed/control parameters
- output artifact writing

The model itself operates in a spatial-temporally compressed latent representation, with a 3D VAE and text conditioning.

SCOS lesson:
Model execution should remain behind an adapter boundary. Production orchestration should not know model internals.

### Open-Sora

The public inference path shows:
- config-driven inference
- distributed environment initialization
- dataset/data-loader abstraction
- model preparation
- prompt refinement
- optional image-condition generation
- sampling API
- artifact save/evaluation pipeline

SCOS lesson:
Prompt refinement, reference conditioning, compute routing, model execution, and artifact writing are separate stages.

### Wan

Wan exposes explicit task modes:
- text-to-video
- image-to-video
- first/last-frame-to-video
- VACE editing
and supports prompt extension, model offload, FSDP, Ulysses/ring parallelism, sampling controls, frame count, size, seed, and output caching.

SCOS lesson:
Capability-aware task routing is a better abstraction than a single universal "generate video" call.

### LTX

The public LTX repository keeps inference thin and pushes configuration into a reusable inference configuration/pipeline. The current repository also exposes synchronized audio-video generation, multiple keyframes, control models, LoRA support, and latent upsampling.

SCOS lesson:
Advanced generation controls should compose around a stable inference contract instead of growing as ad-hoc flags in the UI.

## Common architecture found across the leaders

The strongest shared pattern is:

Creative objective
-> Director planning
-> Story/shot decomposition
-> Reference pack
-> Capability requirements
-> Model/provider routing
-> Async generation tasks
-> Continuity validation
-> Clip artifact sealing
-> Canonical render/composite
-> QC
-> Provenance
-> Telemetry / evaluation

The model is increasingly one stage in a larger production system.

## SCOS gap analysis

Before this upgrade, SCOS already had:
- ProductionGraph
- PremiumMotionGraph
- deterministic fingerprinting
- Remotion rendering
- FFmpeg finishing
- render cache
- asset intelligence
- typography
- compositing
- audio reactivity
- lookdev
- true 3D runtime
- storyboard planning
- benchmark harness
- QC/provenance foundation

The material remaining gap was the layer between storyboard intent and external video-model execution.

## Implemented SCOS upgrade

### scos/premium_media/video_generation.py

Added:
- ReferenceAsset
- ProviderProfile
- ProviderRegistry
- ShotGenerationSpec
- ProviderDecision
- GenerationPlan
- GenerationArtifact
- GenerationTask
- provider capability routing
- director-prompt compilation
- storyboard -> generation-plan compilation
- generation-plan serialization/roundtrip
- fail-closed provider selection
- retryable task state machine

### Canonical provider capability registry

The registry models the current capability surface of:
- Veo 3.1
- Seedance 2.0
- Runway Gen-4.5
- Kling 3.0
- Luma Ray3.14
- Adobe Firefly Video
- MiniMax Hailuo
- Pika
- xAI Grok Imagine Video
- HeyGen Video API

This is a routing abstraction, not a claim that all vendor APIs are already connected.

### ProductionGraph

ProductionGraph now carries generation_plan, fingerprints it, and serializes it into the existing Remotion props boundary.

This keeps the architecture:

CreativeBrief -> Storyboard -> GenerationPlan -> Generated clip assets -> ProductionGraph -> PremiumMotionGraph -> Remotion -> FFmpeg/QC/Provenance

No second orchestration graph was introduced.

## Why this materially raises SCOS capability

SCOS can now express the same high-value control primitives that are repeatedly exposed by leading platforms:
- multimodal reference packs
- character/style continuity
- camera constraints
- motion constraints
- native audio requirements
- first/last-frame requirements
- video-to-video/edit modes
- multi-shot planning
- provider-specific capability routing
- asynchronous generation lifecycle
- artifact sealing before rendering

The important shift is that these controls are now part of the machine-readable production contract rather than only prompt text.

## What is still deliberately not claimed

SCOS does not yet claim:
- direct live API execution against all ten providers
- automatic provider billing/cost optimization
- semantic continuity scoring against every generated frame
- vendor-equivalent safety/moderation systems
- foundation-model training or fine-tuning
- proprietary vendor backend equivalence
- human-level director judgment

Those belong to the next adapter/execution layer.

## Next implementation frontier

The highest-value next development sequence is:

1. Provider execution adapters for the top three targets:
   - Seedance
   - Veo
   - Runway
2. Reference upload/URI materialization and capability-specific input packaging.
3. Async polling/webhook reconciliation into GenerationTask.
4. Generated-clip continuity QC against the existing PremiumMotionGraph.
5. Automatic clip selection and bounded regeneration on failure.
6. Model/provider cost + latency telemetry.
7. Multi-provider A/B generation for high-value shots.
8. Final render orchestration with generated clips, 3D, typography, audio, lookdev, and platform delivery profiles.

The architectural target is not to replace the current renderer. It is to make SCOS the production director that can route the right job to the right generation backend and then bring every result back into one deterministic render/QC/provenance loop.

## Evidence sources

Primary product/platform sources:
- Google DeepMind Veo: https://deepmind.google/models/veo/
- ByteDance Seedance 2.0: https://seed.bytedance.com/en/seedance2_0
- ByteDance Seedance launch: https://seed.bytedance.com/en/blog/seedance-2-0-official-launch
- Runway API docs: https://docs.dev.runwayml.com/guides/using-the-api/
- Luma Ray3 / Modify: https://lumalabs.ai/ray3
- Adobe Firefly partner models: https://helpx.adobe.com/firefly/web/work-with-audio-and-video/work-with-video/generate-videos-using-non-adobe-models.html
- Adobe aerender: https://helpx.adobe.com/after-effects/desktop/render-and-export/automate-rendering/automated-rendering-network-rendering.html
- DaVinci Resolve render queue reference: https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_10_Reference_Manual.pdf
- Remotion: https://www.remotion.dev/

Public/open-source implementation references:
- HunyuanVideo: https://github.com/Tencent-Hunyuan/HunyuanVideo
- Open-Sora: https://github.com/hpcaitech/Open-Sora
- Wan2.1: https://github.com/Wan-Video/Wan2.1
- LTX-Video: https://github.com/Lightricks/LTX-Video

Current market/usage references:
- Vercel AI Gateway video model usage: https://vercel.com/ai-gateway/leaderboards/video/models
- Parallax 2026 AI video comparison: https://parallax.kr/en/blog/most-popular-ai-video-generators-2026
- OpenAI Sora discontinuation notice: https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation

## R10 Governed AI Video Execution Plane â€” 2026-09-20

R10 closes the next architecture gap identified by the Top-3 teardown: SCOS now has a concrete provider execution boundary instead of stopping at capability routing.

Implemented in `scos/premium_media/video_generation_runtime.py`:

- provider adapter protocol with concrete Seedance 2.0, Veo 3.1, and Runway Gen-4.5 adapters
- execution-time capability negotiation that rejects routes failing provider-specific duration, ratio, mode, or reference constraints
- reference byte sealing with SHA-256 validation and provider-specific packaging
- environment-only credential lookup; credentials are never written into plan/journal/evidence artifacts
- asynchronous submit/poll/reconcile lifecycle mapped into the existing GenerationTask state machine
- durable atomic JSON task journal and deterministic idempotency keys
- artifact download, byte sealing, optional media probing, and evidence sealing
- deterministic boundary-frame continuity QC as an explicit proxy metric; failed continuity is fail-closed
- bounded fallback-provider retry
- renderer-facing generated clip manifest `SCOS_GENERATED_CLIP_MANIFEST_R1`
- no external publish path; Human Publish Gate remains NOT_APPROVED

Provider execution was not live-tested because machine-truth currently reports no configured `GEMINI_API_KEY`, `LAS_API_KEY`, or `RUNWAYML_API_SECRET`. The adapter layer is therefore verified with deterministic/fake transports and contract tests, while live vendor execution remains an explicit capability boundary.

This moves the SCOS flow toward:

Creative objective -> Director -> GenerationPlan -> execution negotiation -> async provider task -> sealed clip -> continuity/QC -> generated-clip manifest -> canonical ProductionGraph/Remotion -> FFmpeg delivery -> provenance.

R10 does not claim parity of generated visual quality with any proprietary Top-3 provider. It establishes the production-control architecture required to use those models as interchangeable generation backends.
