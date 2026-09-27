import json
from pathlib import Path

import pytest

from scos.media_analysis.adaptive_smooth_plus_v4 import (
    CalibrationSample,
    build_calibration_profile,
    load_profile,
    save_profile,
    score_candidate,
)
from scos.media_analysis.adaptive_smooth_plus_v3 import CanaryEvidence


def _write_evidence(path: Path, values: list[float]) -> None:
    rows = []
    for value in values:
        rows.append(
            {
                "candidate_metrics": {
                    "path_excess_median": value,
                    "blend_deviation_median": value * 0.5,
                    "asymmetry_median": value * 0.2,
                    "jerk_median": value * 0.1,
                }
            }
        )
    path.write_text(json.dumps(rows), encoding="utf-8")


def _sample(tmp_path: Path, label: str, idx: int, values: list[float]) -> CalibrationSample:
    evidence = tmp_path / f"{label}-{idx}.json"
    _write_evidence(evidence, values)
    return CalibrationSample(
        sample_id=f"{label}-{idx}",
        class_label=label,
        source_path=f"source-{label}-{idx}.mp4",
        source_sha256="0" * 64,
        evidence_path=str(evidence),
        candidate_count=len(values),
    )
def test_profile_balances_multiple_classes(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "desktop_ui", 2, [0.05, 0.06]),
        _sample(tmp_path, "pan_ui", 1, [0.10, 0.11]),
        _sample(tmp_path, "pan_ui", 2, [0.11, 0.12]),
    ]
    profile = build_calibration_profile(samples, min_samples_per_class=2)
    assert set(profile.class_profiles) == {"desktop_ui", "pan_ui"}
    assert profile.class_counts["desktop_ui"] == 4
    assert profile.class_counts["pan_ui"] == 4


def test_profile_fails_closed_for_small_class(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "pan_ui", 1, [0.10]),
    ]
    with pytest.raises(ValueError, match="need 2"):
        build_calibration_profile(samples, min_samples_per_class=2)


def test_profile_round_trip(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "desktop_ui", 2, [0.05, 0.06]),
    ]
    profile = build_calibration_profile(samples)
    target = tmp_path / "profile.json"
    save_profile(target, profile)
    loaded = load_profile(target)
    assert loaded.profile_id == profile.profile_id
    assert loaded.class_counts == profile.class_counts


def test_unknown_class_fails_closed(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "desktop_ui", 2, [0.05, 0.06]),
    ]
    profile = build_calibration_profile(samples)
    evidence = CanaryEvidence(
        0.0, 1.0, 0.3, 0.7, 2, 1.0,
        {}, {"path_excess_median": 0.05, "blend_deviation_median": 0.02,
              "asymmetry_median": 0.01, "jerk_median": 0.005},
        {}, {}, 1.0, "SMOOTH+"
    )
    with pytest.raises(ValueError, match="unknown calibration class"):
        score_candidate(evidence, "talking_head", profile)
def test_candidate_outlier_is_review(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "desktop_ui", 2, [0.05, 0.06]),
    ]
    profile = build_calibration_profile(samples, z_review=3.0)
    evidence = CanaryEvidence(
        0.0, 1.0, 0.3, 0.7, 2, 1.0,
        {}, {"path_excess_median": 1.5, "blend_deviation_median": 0.75,
              "asymmetry_median": 0.3, "jerk_median": 0.15},
        {}, {}, 1.0, "SMOOTH+"
    )
    scored = score_candidate(evidence, "desktop_ui", profile)
    assert scored["decision"] == "REVIEW"
    assert "v4_class_temporal_outlier" in scored["reasons"]
def test_candidate_within_class_is_smooth(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "desktop_ui", 1, [0.04, 0.05]),
        _sample(tmp_path, "desktop_ui", 2, [0.05, 0.06]),
    ]
    profile = build_calibration_profile(samples)
    evidence = CanaryEvidence(
        0.0, 1.0, 0.3, 0.7, 2, 1.0,
        {}, {"path_excess_median": 0.055, "blend_deviation_median": 0.0275,
              "asymmetry_median": 0.011, "jerk_median": 0.0055},
        {}, {}, 1.0, "SMOOTH+"
    )
    scored = score_candidate(evidence, "desktop_ui", profile)
    assert scored["decision"] == "SMOOTH+"

def _write_labeled_evidence(path: Path, *, quality: float, decision: str) -> None:
    path.write_text(
        json.dumps([{
            "quality_score": quality,
            "decision": decision,
            "sample_count": 8,
            "valid_triple_ratio": 1.0,
            "candidate_metrics": {
                "path_excess_median": 0.05 if decision == "SMOOTH+" else 0.20,
                "blend_deviation_median": 0.02 if decision == "SMOOTH+" else 0.10,
                "asymmetry_median": 0.01 if decision == "SMOOTH+" else 0.20,
                "jerk_median": 0.001 if decision == "SMOOTH+" else 0.01,
            },
        }]),
        encoding="utf-8",
    )


def test_loso_global_fallback_generalizes_unseen_positive_without_false_accept(tmp_path: Path) -> None:
    from scos.media_analysis.adaptive_smooth_plus_v4 import leave_one_source_out

    samples = []
    specs = [
        ("class_a", "a-review-1", 0.10, "REVIEW"),
        ("class_a", "a-review-2", 0.20, "REVIEW"),
        ("class_a", "a-positive-3", 0.90, "SMOOTH+"),
        ("class_b", "b-positive-1", 0.95, "SMOOTH+"),
        ("class_b", "b-review-2", 0.15, "REVIEW"),
        ("class_b", "b-review-3", 0.25, "REVIEW"),
    ]
    for label, sid, quality, decision in specs:
        evidence = tmp_path / f"{sid}.json"
        _write_labeled_evidence(evidence, quality=quality, decision=decision)
        samples.append(
            CalibrationSample(
                sample_id=sid,
                class_label=label,
                source_path=f"{sid}.mp4",
                source_sha256=sid + ("0" * (64 - len(sid))),
                evidence_path=str(evidence),
                reference_decision=decision,
                candidate_count=1,
            )
        )

    result = leave_one_source_out(samples, min_training_sources=2, z_review=4.0)
    assert result["overall"] == "PASS"
    assert result["positive_retention"] == 1.0
    assert result["negative_rejection"] == 1.0
    assert result["false_accept_count"] == 0
    assert result["source_level_leakage"] is False
    assert result["global_fallback_fold_count"] >= 2
