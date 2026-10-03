# Premium R16 — Effects / Audio / Subtitles / Multi-Format Evidence

Date: 2026-09-20
Worktree: `feat/premium-motion-grammar-r1`
Scope: close the production-capability gap before promoting the deterministic Hermes/AISL post-work skill candidate.
## Changes closed

- MotionGraph runtime now carries music and SFX into the canonical Remotion path.
- `EffectStack.vignette` and `EffectStack.grain` now produce pixels; audio-reactive strength also modulates motion scale.
- `dip_to_black` / `dip_to_white` transitions now match the canonical transition names and render a visual dip.
- `PremiumSingleScreen` now derives duration, FPS and canvas geometry from props.
- Canonical backend safe-zone preflight is geometry-relative instead of vertical-pixel hard-coded.
- Delivery profiles now include vertical, horizontal, square and 4:5 master targets plus horizontal YouTube delivery.
- ASS subtitle generation now honors `SubtitleStyle.position` for 9 standard positions and fails closed on unsupported values.
## Real render evidence

Remotion-native capability smoke rendered 120/120 frames for each target:

| Target | Geometry | FPS | Audio | Result |
|---|---:|---:|---|---|
| Vertical | 1080x1920 | 30 | AAC 48 kHz stereo | PASS |
| Landscape | 1920x1080 | 30 | AAC 48 kHz stereo | PASS |
| Square | 1080x1080 | 30 | AAC 48 kHz stereo | PASS |
Those outputs were generated from the same production graph with motion effects, music, SFX, captions, kinetic typography and a dip transition. This is native renderer geometry, not only a post-render resize.

The canonical finalization smoke then produced a sealed 1080x1920 MP4 at exactly 4.0s and passed `validate_render` with no errors or warnings. Delivery transcode was also proven to produce 1920x1080 and 1080x1080 artifacts with 30fps H.264 + AAC 48 kHz stereo.
## Verification

- Premium Media regression: **59 passed**.
- `scos/render/tests`: **6 passed**.
- `python -m compileall -q scos`: **PASS**.
- `git diff --check`: **PASS**.

A full repository pytest run was attempted and surfaced a six-error cluster around 21% before a traceback was captured. Attribution to R16 was not established, so that run is not treated as a clean certification. The directly affected Premium Media and Render suites are green.
## Capability boundary

The requested effects/audio/subtitle foundation is now operational enough for the current SCOS production loop: deterministic motion/effects, compositing, masks, real audio mix/reactivity, burned-in subtitles, kinetic typography, 3D scene support, generated-clip assembly, QC, and multiple native canvas targets.

Known non-blocking advanced gap: `crossfade` is currently implemented as opacity fading within the non-overlapping shot grammar, not a true simultaneous overlap between two shots. True overlap-based crossfades require an explicit timeline-overlap model and should be a later capability increment rather than hidden behind the current schema.
## Next skill candidate

After this capability closure, the highest-value mechanical candidate remains the deterministic Hermes/AISL capability for `task reconciliation → artifact sealing → clip staging → telemetry → evidence`, because those operations are now repeated across the production loop and can be extracted without moving Human governance gates.
