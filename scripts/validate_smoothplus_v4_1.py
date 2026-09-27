from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from scos.media_analysis.adaptive_smooth_plus_v4 import (
    CalibrationSample,
    build_calibration_profile,
    leave_one_source_out,
    save_profile,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "media-pipeline-adaptive-v4.1"
MANIFEST = EVIDENCE / "V4_1_CORPUS_MANIFEST.json"


def load_samples() -> list[CalibrationSample]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    samples: list[CalibrationSample] = []

    for row in data["samples"]:
        samples.append(
            CalibrationSample(
                sample_id=row["sample_id"],
                class_label=row["class_label"],
                source_path=row["source_path"],
                source_sha256=row["source_sha256"],
                evidence_path=row["evidence_path"],
                reference_decision=row["reference_decision"],
                canary_index=int(row["canary_index"]),
                source_family_id=row["source_family_id"],
            )
        )
    return samples


def main() -> None:
    samples = load_samples()

    source_by_class: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        actual_sha = sha256_file(sample.source_path)
        if actual_sha.lower() != sample.source_sha256.lower():
            raise RuntimeError(f"source SHA changed: {sample.source_path}")
        source_by_class[sample.class_label].add(sample.source_sha256)

    source_counts = {label: len(values) for label, values in sorted(source_by_class.items())}
    if any(count < 3 for count in source_counts.values()):
        raise RuntimeError(f"V4.1 requires at least 3 independent sources per class: {source_counts}")

    # Diagnostic profile only. Production/generalization authority comes from LOSO.
    # Some classes may currently have only one accepted source, which is not enough
    # for a production fold but is still useful to persist as corpus evidence.
    profile = build_calibration_profile(
        [s for s in samples if s.reference_decision == "SMOOTH+"],
        min_training_sources=1,
        z_review=6.0,
    )
    save_profile(EVIDENCE / "V4_1_CALIBRATION_PROFILE.json", profile)

    loso = leave_one_source_out(
        samples,
        min_training_sources=2,
        z_review=6.0,
    )

    report = {
        "schema": 1,
        "phase": "Adaptive SMOOTH+ V4.1 Multi-Class Calibration Corpus",
        "source_counts_by_class": source_counts,
        "unique_source_count": len({s.source_sha256 for s in samples}),
        "canary_observation_count": len(samples),
        "profile_id": profile.profile_id,
        "profile_training_sources": profile.source_count,
        "profile_observations": profile.observation_count,
        "reference_decision_counts": {
            "SMOOTH+": sum(s.reference_decision == "SMOOTH+" for s in samples),
            "REVIEW": sum(s.reference_decision == "REVIEW" for s in samples),
        },
        "loso": loso,
        "safety": {
            "source_sha_verification": "PASS",
            "minimum_sources_per_class": 3,
            "training_sources_per_fold": 2,
            "automatic_promotion": "DISABLED",
            "v4_calibration_authority": "OFFLINE_REVIEW_ONLY",
        },
        "limitations": [
            "The screen_recording_real and portrait_screen_real classes are screen/UI families; "
            "they should not be interpreted as natural-scene calibration.",
            "Natural motion uses three independent open Blender movie sources.",
            "LOSO evaluates generalization against V3 reference decisions; it is not human MOS ground truth.",
            "V4.1 must not override V3 safety gates.",
        ],
        "research_basis": [
            "Vimeo-90K was designed for temporal frame interpolation and covers varied scenes/actions.",
            "Recent VFI quality work reports that generic PSNR/SSIM can miss interpolation-specific temporal artifacts.",
        ],
    }

    (EVIDENCE / "V4_1_LOSO_VALIDATION_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "overall": loso["overall"],
        "source_counts": source_counts,
        "folds": loso["fold_count"],
        "eligible_folds": loso["eligible_fold_count"],
        "positive_retention": loso["positive_retention"],
        "negative_rejection": loso["negative_rejection"],
        "profile_id": profile.profile_id,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
