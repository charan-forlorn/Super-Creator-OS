# SCOS Adaptive SMOOTH+ V4 — Multi-Class Calibration Corpus
## 2026-09-27

## Objective
V4 adds an offline, deterministic calibration layer above the V3 temporal canary.
It does not replace V3 routing yet. It learns class-specific temporal distributions
from verified RIFE canaries and scores new candidates against those distributions.

## Research basis
Recent VFI quality-assessment work notes that ordinary full-reference metrics can
miss interpolation-specific temporal artifacts. CLIP-Fusion (WACV 2025) explicitly
targets spatio-temporal interpolation artifacts, while TLB-VFI (ICCV 2025) reports
that PSNR/SSIM can be weakly aligned with perceived VFI quality and includes
motion-aware perceptual evaluation. A WACV 2025 study also highlights the
difficulty of discontinuous motions such as UI overlays and subtitles.

## Implementation
- `scos/media_analysis/adaptive_smooth_plus_v4.py`
- `scos/media_analysis/tests/test_adaptive_smooth_plus_v4.py`
- `scripts/calibrate_smoothplus_v4.py`
- `evidence/media-pipeline-adaptive-v4/V4_CORPUS_MANIFEST.json`
- `evidence/media-pipeline-adaptive-v4/V4_CALIBRATION_PROFILE.json`
- `evidence/media-pipeline-adaptive-v4/V4_VALIDATION_REPORT.json`
## Current corpus
The verified local corpus contains three real screen-oriented classes and six
accepted canary observations:
- `screen_mixed_real`: 2 observations
- `screen_remix_real`: 2 observations
- `vertical_remaster_real`: 2 observations

Every manifest source SHA-256 matched its current source bytes during validation.

The calibration profile uses robust median/MAD statistics for:
- path excess
- blend deviation
- asymmetry
- jerk

Unknown classes fail closed. Candidate values above the class robust-z threshold
remain `REVIEW`; the profile never grants execution authority by itself.

## Validation
- V4 unit tests: 6 passed.
- Full `scos` regression after V4: 2863 passed, 21 skipped, 21 deselected.
- Four in-domain positive holdouts scored `SMOOTH+`.
- Two known negative/outlier holdouts scored `REVIEW`.
- Unknown class guard: PASS / fail-closed.
- Source hash verification: PASS for every corpus sample.
## Important limitation
This is a calibration proof, not a promotion proof.

The current corpus has only one unique source file per class, is strongly
screen-oriented, and has no local talking-head source. Therefore V4 remains an
offline REVIEW calibration layer and automatic promotion remains disabled.

The next corpus expansion should add independent source files per class and at
least one genuinely different motion family before V4 thresholds are allowed
to influence production routing autonomously.

## Operational rule
V3 remains the active experimental quality gate. V4 is used to measure whether
class-conditioned calibration reduces false rejection and false acceptance over
a broader corpus. Any disagreement between deterministic V3 safety and V4
calibration resolves to the safer V3 / REVIEW outcome.
## Reproducibility
Run from the repository root with the project virtual environment:

`python -m scripts.calibrate_smoothplus_v4`

The command:
1. loads the signed-by-hash corpus manifest,
2. verifies current source hashes,
3. loads the V4 calibration profile,
4. scores positive and negative holdouts,
5. verifies unknown-class fail-closed behavior,
6. writes `V4_VALIDATION_REPORT.json`.

Automatic promotion is intentionally not performed by this script.
