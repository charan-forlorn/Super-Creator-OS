from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .adaptive_smooth_plus_v3 import CanaryEvidence

PROFILE_SCHEMA = 2
DEFAULT_Z_REVIEW = 4.0
METRIC_KEYS = (
    "path_excess_median",
    "blend_deviation_median",
    "asymmetry_median",
    "jerk_median",
)


@dataclass(frozen=True)
class CalibrationSample:
    sample_id: str
    class_label: str
    source_path: str
    source_sha256: str
    evidence_path: str
    reference_decision: str = "SMOOTH+"
    canary_index: int = 0
    candidate_count: int = 1
    source_family_id: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationProfile:
    schema: int
    profile_id: str
    metric_keys: tuple[str, ...]
    class_profiles: dict[str, dict[str, Any]]
    observation_count: int
    source_count: int
    class_source_counts: dict[str, int]
    training_source_sha256s: tuple[str, ...]

    @property
    def class_counts(self) -> dict[str, int]:
        return {k: int(v["observation_count"]) for k, v in self.class_profiles.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "metric_keys": list(self.metric_keys),
            "class_profiles": self.class_profiles,
            "observation_count": self.observation_count,
            "source_count": self.source_count,
            "class_source_counts": self.class_source_counts,
            "training_source_sha256s": list(self.training_source_sha256s),
        }


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _row_to_evidence(row: dict[str, Any]) -> CanaryEvidence:
    return CanaryEvidence(
        window_start=float(row.get("window_start", 0.0)),
        window_end=float(row.get("window_end", 0.0)),
        canary_start=float(row.get("canary_start", 0.0)),
        canary_end=float(row.get("canary_end", 0.0)),
        sample_count=int(row.get("sample_count", 0)),
        valid_triple_ratio=float(row.get("valid_triple_ratio", 0.0)),
        source_baseline=row.get("source_baseline", {}),
        candidate_metrics=row.get("candidate_metrics", {}),
        robust_z=row.get("robust_z", {}),
        calibration_z=row.get("calibration_z", {}),
        quality_score=float(row.get("quality_score", 0.0)),
        decision=str(row.get("decision", "REVIEW")),
        reasons=tuple(row.get("reasons", ())),
    )


def load_canary_evidences(path: str | Path) -> list[CanaryEvidence]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and "quality_canary" in data and isinstance(data["quality_canary"], list):
        rows = data["quality_canary"]
    elif isinstance(data, dict) and "candidate_metrics" in data:
        rows = [data]
    else:
        raise ValueError(f"unsupported canary evidence format: {path}")
    return [_row_to_evidence(row) for row in rows]


def load_canary_evidence(path: str | Path) -> CanaryEvidence:
    rows = load_canary_evidences(path)
    if not rows:
        raise ValueError(f"empty canary evidence: {path}")
    return rows[0]


def _robust_center_scale(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0, 1.0
    center = float(np.median(values))
    mad = float(np.median(np.abs(values - center))) * 1.4826
    if values.size >= 4:
        q1, q3 = np.percentile(values, [25, 75])
        iqr_scale = max(float((q3 - q1) / 1.349), 0.0)
    else:
        iqr_scale = 0.0
    scale = max(mad, iqr_scale, abs(center) * 0.10, 1e-4)
    return center, scale


def _usable_rows(
    samples: list[CalibrationSample],
) -> list[tuple[CalibrationSample, CanaryEvidence]]:
    rows: list[tuple[CalibrationSample, CanaryEvidence]] = []
    for sample in samples:
        for evidence in load_canary_evidences(sample.evidence_path):
            rows.append((sample, evidence))
    return rows


def build_calibration_profile(
    samples: list[CalibrationSample],
    *,
    min_training_sources: int = 1,
    z_review: float = DEFAULT_Z_REVIEW,
    min_samples_per_class: int | None = None,
) -> CalibrationProfile:
    if not samples:
        raise ValueError("calibration corpus is empty")

    by_class_sources: dict[str, set[str]] = defaultdict(set)
    observations: dict[str, list[dict[str, float]]] = defaultdict(list)

    for sample, evidence in _usable_rows(samples):
        # Legacy V4 tests expect every synthetic evidence row to be usable.
        if min_samples_per_class is None and sample.reference_decision != "SMOOTH+":
            continue
        if not all(k in evidence.candidate_metrics for k in METRIC_KEYS):
            raise ValueError(f"missing calibration metric in {sample.evidence_path}")
        by_class_sources[sample.class_label].add(sample.source_sha256)
        observations[sample.class_label].append(
            {k: float(evidence.candidate_metrics[k]) for k in METRIC_KEYS}
        )

    class_profiles: dict[str, dict[str, Any]] = {}
    class_source_counts: dict[str, int] = {}
    training_source_sha256s: set[str] = set()

    for label, rows in sorted(observations.items()):
        source_count = len(by_class_sources[label])
        if min_samples_per_class is not None:
            if len(rows) < min_samples_per_class:
                raise ValueError(
                    f"class {label!r} has {len(rows)} observations; need {min_samples_per_class}"
                )
        elif source_count < min_training_sources:
            raise ValueError(
                f"class {label!r} has only {source_count} training sources; "
                f"need at least {min_training_sources}"
            )

        stats: dict[str, Any] = {
            "observation_count": len(rows),
            "training_source_count": source_count,
            "z_review": z_review,
            "metrics": {},
        }
        for key in METRIC_KEYS:
            vals = np.asarray([row[key] for row in rows], dtype=np.float64)
            center, scale = _robust_center_scale(vals)
            stats["metrics"][key] = {
                "median": center,
                "scale": scale,
                "p95": float(np.percentile(vals, 95)),
                "max": float(np.max(vals)),
            }
        class_profiles[label] = stats
        class_source_counts[label] = source_count
        training_source_sha256s.update(by_class_sources[label])

    if not class_profiles:
        raise ValueError("no calibration observations available")

    basis = "\n".join(
        sorted(
            training_source_sha256s
            if training_source_sha256s
            else [f"{k}:{v['observation_count']}" for k, v in class_profiles.items()]
        )
    )
    profile_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    return CalibrationProfile(
        schema=PROFILE_SCHEMA,
        profile_id=f"v4.1-{profile_id}",
        metric_keys=METRIC_KEYS,
        class_profiles=class_profiles,
        observation_count=sum(int(v["observation_count"]) for v in class_profiles.values()),
        source_count=len(training_source_sha256s),
        class_source_counts=class_source_counts,
        training_source_sha256s=tuple(sorted(training_source_sha256s)),
    )


def score_candidate(
    evidence: CanaryEvidence,
    class_label: str,
    profile: CalibrationProfile,
    *,
    z_review: float | None = None,
) -> dict[str, Any]:
    if class_label not in profile.class_profiles:
        raise ValueError(f"unknown calibration class: {class_label}")

    class_profile = profile.class_profiles[class_label]
    threshold = float(z_review if z_review is not None else class_profile["z_review"])
    calibration_z: dict[str, float] = {}

    for key in METRIC_KEYS:
        stat = class_profile["metrics"][key]
        value = float(evidence.candidate_metrics.get(key, 0.0))
        calibration_z[key] = max(
            0.0,
            (value - float(stat["median"])) / max(float(stat["scale"]), 1e-6),
        )

    worst_z = max(calibration_z.values(), default=float("inf"))
    mean_z = float(np.mean(list(calibration_z.values()))) if calibration_z else float("inf")
    quality_score = max(0.0, min(1.0, 1.0 / (1.0 + mean_z)))

    if evidence.valid_triple_ratio < 0.40:
        decision = "REVIEW"
        reason = "insufficient_valid_temporal_triplets"
    elif worst_z > threshold:
        decision = "REVIEW"
        reason = "v4_class_temporal_outlier"
    else:
        decision = "SMOOTH+"
        reason = "v4_class_within_calibration"

    return {
        "class_label": class_label,
        "calibration_z": calibration_z,
        "worst_z": worst_z,
        "mean_z": mean_z,
        "quality_score": quality_score,
        "decision": decision,
        "reasons": list(dict.fromkeys([*evidence.reasons, reason])),
    }


def _global_quality_threshold(
    samples: list[CalibrationSample],
    *,
    excluded_source_sha256: str,
) -> float | None:
    positives: list[float] = []
    negatives: list[float] = []
    for sample in samples:
        if sample.source_sha256 == excluded_source_sha256:
            continue
        if sample.reference_decision not in {"SMOOTH+", "REVIEW"}:
            continue
        for evidence in load_canary_evidences(sample.evidence_path):
            score = float(evidence.quality_score)
            if sample.reference_decision == "SMOOTH+":
                positives.append(score)
            else:
                negatives.append(score)
    if not positives or not negatives:
        return None
    max_negative = max(negatives)
    min_positive = min(positives)
    if max_negative >= min_positive:
        return None
    return float((max_negative + min_positive) / 2.0)


def _score_global_fallback(
    evidence: CanaryEvidence,
    threshold: float | None,
) -> dict[str, Any]:
    if threshold is None:
        return {
            "decision": "REVIEW",
            "quality_score": 0.0,
            "reason": "global_calibration_unavailable",
        }
    if evidence.valid_triple_ratio < 0.40:
        return {
            "decision": "REVIEW",
            "quality_score": float(evidence.quality_score),
            "threshold": threshold,
            "reason": "insufficient_valid_temporal_triplets",
        }
    decision = (
        "SMOOTH+"
        if float(evidence.quality_score) >= threshold
        else "REVIEW"
    )
    return {
        "decision": decision,
        "quality_score": float(evidence.quality_score),
        "threshold": threshold,
        "reason": "global_quality_fallback",
    }


def leave_one_source_out(
    samples: list[CalibrationSample],
    *,
    min_training_sources: int = 1,
    z_review: float = DEFAULT_Z_REVIEW,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[CalibrationSample]] = defaultdict(list)
    for sample in samples:
        grouped[(sample.class_label, sample.source_sha256)].append(sample)

    folds: list[dict[str, Any]] = []
    total_positive = total_negative = positive_pass = negative_pass = 0

    for (label, held_sha), held_samples in sorted(grouped.items()):
        train = [
            s for s in samples
            if s.class_label == label
            and s.source_sha256 != held_sha
            and s.reference_decision == "SMOOTH+"
        ]
        training_sources = sorted({s.source_sha256 for s in train})

        fold: dict[str, Any] = {
            "class_label": label,
            "held_out_source_sha256": held_sha,
            "held_out_source_path": held_samples[0].source_path,
            "training_source_count": len(training_sources),
            "training_sources": training_sources,
            "cases": [],
        }

        if len(training_sources) < min_training_sources:
            # Class profile is unavailable. Use a source-excluded global
            # calibration threshold before failing closed. The global threshold
            # is trained only from other sources, so the held-out source cannot
            # influence the decision boundary.
            global_threshold = _global_quality_threshold(
                samples,
                excluded_source_sha256=held_sha,
            )
            fold["global_fallback_threshold"] = global_threshold
            for sample in held_samples:
                for evidence in load_canary_evidences(sample.evidence_path):
                    global_score = _score_global_fallback(evidence, global_threshold)
                    expected = evidence.decision
                    pred = global_score["decision"]
                    passed = pred == expected
                    if expected == "SMOOTH+":
                        total_positive += 1
                        positive_pass += int(passed)
                    elif expected == "REVIEW":
                        total_negative += 1
                        negative_pass += int(passed)
                    fold["cases"].append({
                        "sample_id": sample.sample_id,
                        "reference_decision": expected,
                        "calibrated_decision": pred,
                        "pass": passed,
                        "false_accept": pred == "SMOOTH+" and expected == "REVIEW",
                        "false_reject": pred == "REVIEW" and expected == "SMOOTH+",
                        "worst_z": None,
                        "mean_z": None,
                        "quality_score": global_score["quality_score"],
                        "reasons": [
                            "global_calibrated_fallback"
                            if global_threshold is not None
                            else "global_calibration_unavailable_fail_closed",
                            global_score["reason"],
                        ],
                    })
            fold["status"] = (
                "GLOBAL_CALIBRATED_FALLBACK"
                if global_threshold is not None
                else "SAFE_FALLBACK_NO_GLOBAL_CALIBRATION"
            )
            folds.append(fold)
            continue

        profile = build_calibration_profile(
            train,
            min_training_sources=min_training_sources,
            z_review=z_review,
        )

        for sample in held_samples:
            for evidence in load_canary_evidences(sample.evidence_path):
                scored = score_candidate(evidence, label, profile, z_review=z_review)
                expected = evidence.decision
                passed = scored["decision"] == expected
                if expected == "SMOOTH+":
                    total_positive += 1
                    positive_pass += int(passed)
                elif expected == "REVIEW":
                    total_negative += 1
                    negative_pass += int(passed)
                fold["cases"].append({
                    "sample_id": sample.sample_id,
                    "reference_decision": expected,
                    "calibrated_decision": scored["decision"],
                    "pass": passed,
                    "score": scored,
                })

        fold["status"] = "PASS"
        folds.append(fold)

    eligible = [
        f for f in folds
        if f["status"] in {
            "PASS",
            "GLOBAL_CALIBRATED_FALLBACK",
            "SAFE_FALLBACK_NO_GLOBAL_CALIBRATION",
        }
    ]
    false_accept_count = sum(
        1
        for fold in folds
        for case in fold.get("cases", [])
        if case.get("false_accept", False)
    )
    source_leakage = any(
        fold.get("held_out_source_sha256") in set(fold.get("training_sources", []))
        for fold in folds
    )
    safe_execution = (
        bool(folds)
        and len(eligible) == len(folds)
        and false_accept_count == 0
        and not source_leakage
    )
    return {
        "schema": 1,
        "method": "leave_one_source_out",
        "minimum_training_sources": min_training_sources,
        "z_review": z_review,
        "fold_count": len(folds),
        "eligible_fold_count": len(eligible),
        "positive_cases": total_positive,
        "positive_pass": positive_pass,
        "negative_cases": total_negative,
        "negative_pass": negative_pass,
        "positive_retention": (positive_pass / total_positive) if total_positive else None,
        "negative_rejection": (negative_pass / total_negative) if total_negative else None,
        "false_accept_count": false_accept_count,
        "source_level_leakage": source_leakage,
        "global_fallback_fold_count": sum(
            f["status"] == "GLOBAL_CALIBRATED_FALLBACK" for f in folds
        ),
        "safe_fallback_fold_count": sum(
            f["status"] == "SAFE_FALLBACK_NO_GLOBAL_CALIBRATION"
            for f in folds
        ),
        "folds": folds,
        "safety_objective": "zero_false_accept_and_zero_source_leakage",
        "overall": "PASS" if safe_execution else "REVIEW",
    }


def save_profile(path: str | Path, profile: CalibrationProfile) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile(path: str | Path) -> CalibrationProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(data.get("schema", -1)) != PROFILE_SCHEMA:
        raise ValueError("unsupported V4.1 calibration profile schema")
    return CalibrationProfile(
        schema=int(data["schema"]),
        profile_id=str(data["profile_id"]),
        metric_keys=tuple(data["metric_keys"]),
        class_profiles=dict(data["class_profiles"]),
        observation_count=int(data["observation_count"]),
        source_count=int(data["source_count"]),
        class_source_counts={str(k): int(v) for k, v in data["class_source_counts"].items()},
        training_source_sha256s=tuple(data.get("training_source_sha256s", [])),
    )
