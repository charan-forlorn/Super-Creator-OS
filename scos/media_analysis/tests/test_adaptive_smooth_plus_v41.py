from __future__ import annotations

import json
from pathlib import Path

from scos.media_analysis.adaptive_smooth_plus_v4 import (
    CalibrationSample,
    leave_one_source_out,
)
from scos.media_analysis.adaptive_smooth_plus_v3 import CanaryEvidence


def _write_case(path: Path, decision: str, value: float) -> None:
    payload = CanaryEvidence(
        window_start=1.0,
        window_end=2.0,
        canary_start=1.2,
        canary_end=1.6,
        sample_count=4,
        valid_triple_ratio=0.75,
        source_baseline={},
        candidate_metrics={
            "path_excess_median": value,
            "blend_deviation_median": value / 2,
            "asymmetry_median": value / 3,
            "jerk_median": value / 10,
        },
        robust_z={},
        calibration_z={},
        quality_score=1.0 if decision == "SMOOTH+" else 0.1,
        decision=decision,
        reasons=(),
    )
    path.write_text(json.dumps(payload.to_dict()), encoding="utf-8")


def _sample(tmp_path: Path, sid: str, decision: str, value: float) -> CalibrationSample:
    sha = sid * 64
    path = tmp_path / f"{sid}.json"
    _write_case(path, decision, value)
    return CalibrationSample(
        sample_id=sid,
        class_label="test_class",
        source_path=f"{sid}.mp4",
        source_sha256=sha[:64],
        evidence_path=str(path),
        reference_decision=decision,
        source_family_id=sha[:64],
    )


def test_loso_has_no_source_leakage(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "a", "SMOOTH+", 0.05),
        _sample(tmp_path, "b", "SMOOTH+", 0.06),
        _sample(tmp_path, "c", "SMOOTH+", 0.07),
        _sample(tmp_path, "d", "REVIEW", 0.5),
    ]
    result = leave_one_source_out(samples, min_training_sources=2)
    assert result["source_level_leakage"] is False


def test_loso_counts_all_source_folds(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "a", "SMOOTH+", 0.05),
        _sample(tmp_path, "b", "SMOOTH+", 0.06),
        _sample(tmp_path, "c", "SMOOTH+", 0.07),
        _sample(tmp_path, "d", "REVIEW", 0.5),
    ]
    result = leave_one_source_out(samples, min_training_sources=2)
    assert result["fold_count"] == 4
    assert result["eligible_fold_count"] == 4


def test_loso_never_accepts_known_review_without_leakage(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "a", "SMOOTH+", 0.05),
        _sample(tmp_path, "b", "SMOOTH+", 0.06),
        _sample(tmp_path, "c", "SMOOTH+", 0.07),
        _sample(tmp_path, "d", "REVIEW", 0.9),
    ]
    result = leave_one_source_out(samples, min_training_sources=2)
    assert result["false_accept_count"] == 0


def test_loso_report_is_source_level(tmp_path: Path) -> None:
    samples = [
        _sample(tmp_path, "a", "SMOOTH+", 0.05),
        _sample(tmp_path, "b", "SMOOTH+", 0.06),
        _sample(tmp_path, "c", "SMOOTH+", 0.07),
    ]
    result = leave_one_source_out(samples, min_training_sources=2)
    held_out = {f["held_out_source_sha256"] for f in result["folds"]}
    trained = {
        sha
        for f in result["folds"]
        for sha in f.get("training_sources", [])
    }
    assert held_out.isdisjoint(trained) is False or result["source_level_leakage"] is False
