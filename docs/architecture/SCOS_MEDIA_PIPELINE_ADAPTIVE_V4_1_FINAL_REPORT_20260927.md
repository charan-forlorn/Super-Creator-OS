# SCOS Adaptive SMOOTH+ V4.1 - Multi-Class Calibration Corpus

## Finalization - 2026-09-27

V4.1 uses 9 independent source files across 3 classes and 18 canary observations. Compared with the prior V4 corpus, screen_recording_real adds 2 new source files, portrait_screen_real adds 2 new source files, and natural_motion_real adds 3 new source files while introducing a distinct motion family.

### LOSO

Validation is leave-one-source-out at complete source-file level. A held-out source SHA never enters its training fold. Calibration precedence is class-conditioned profile -> source-excluded global calibrated fallback -> REVIEW.

Final result:
- 9 folds
- 18 held-out canaries
- 100% positive retention
- 100% negative rejection
- 0 false accepts
- 0 source leakage
- overall PASS

### Verification

- V4.1 unit tests: 7 passed
- Full scos regression: 2864 passed, 21 skipped, 21 deselected
- Python compile: PASS
- Automatic promotion: DISABLED

V4.1 remains offline/review-only. The V3 deterministic safety gates remain authoritative.
