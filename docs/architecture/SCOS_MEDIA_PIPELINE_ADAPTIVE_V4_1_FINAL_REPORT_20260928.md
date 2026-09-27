# SCOS Adaptive SMOOTH+ V4.1 — Multi-Class Calibration Corpus + LOSO
## 2026-09-28

## Objective
V4.1 tests whether the V4 temporal calibration layer generalizes to genuinely unseen source files instead of reusing observations from the same source file.

The phase adds:
- at least two new source files versus V4 for every calibration class;
- an additional motion family;
- source-level SHA-256 identity;
- leave-one-source-out (LOSO) validation;
- an evidence-based calibration threshold sweep;
- zero-false-accept safety as the primary gate.

## Corpus
| Class | Sources | New vs V4 |
|---|---:|---:|
| screen_recording_real | 3 | 2 |
| portrait_screen_real | 4 | 2 |
| natural_motion_real | 3 | 3 |
| **Total** | **10** | **7** |

The corpus contains 20 canary observations. Every source is identified by SHA-256 and current source bytes were verified against the manifest.

The natural_motion_real class is the intentionally different motion family. It contains independent animation/natural-motion sources and is not treated as a screen/UI proxy.

## Threshold calibration
The LOSO threshold was swept over:
4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0, 10.0.

Observed plateau:
- z=5.5 through z=10.0: 100% positive retention;
- z=5.5 through z=10.0: 100% negative rejection;
- zero false accepts.

V4.1 therefore uses z_review = 6.0.

V3 remains authoritative for deterministic safety. V4.1 cannot promote a window that V3 rejects; the calibration profile is an offline review/calibration layer.

## Leave-One-Source-Out result
- Fold count: 10
- Eligible folds: 10
- Positive cases: 11
- Positive pass: 11
- Positive retention: 100%
- Negative cases: 9
- Negative pass: 9
- Negative rejection: 100%
- False accepts: 0
- False rejects: 0
- Source-level leakage: false
- Global source-excluded fallback folds: 5
- Safe fallback folds: 0
- Overall: PASS

The global fallback is source-excluded per fold. It never uses the held-out source to set the fallback boundary.

## Regression
- V4.1 focused tests: 11 passed.
- Full SCOS regression: 2868 passed, 21 skipped, 21 deselected.
- compileall: PASS.
- Focused py_compile: PASS.

During reconciliation, stale literal-\\n corruption was found in pre-existing V3/V2 test/source files. It was normalized deterministically and the full SCOS regression was re-run successfully. No V4.1 evidence was accepted while the imported V2/V3 modules were syntactically invalid.

## Promotion state
Automatic promotion remains DISABLED.

V4.1 establishes source-level generalization evidence, not human perceptual ground truth. The next promotion phase should correlate deterministic outcomes with independent perceptual/quality evidence before changing production routing.

## Reproducibility
Run from repository root:

python -m scripts.validate_smoothplus_v4_1

Expected V4.1 gate:
- 3+ independent sources/class;
- 2+ newly introduced sources/class versus V4;
- 10+ source-level folds for the current corpus;
- zero source leakage;
- zero false accepts;
- 100% positive retention on the current reference corpus;
- automatic promotion disabled.
