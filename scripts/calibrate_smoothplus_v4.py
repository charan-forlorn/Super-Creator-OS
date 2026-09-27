from __future__ import annotations

import json
from pathlib import Path

from scos.media_analysis.adaptive_smooth_plus_v3 import CanaryEvidence
from scos.media_analysis.adaptive_smooth_plus_v4 import (
    load_profile,
    score_candidate,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "media-pipeline-adaptive-v4"
PROFILE_PATH = EVIDENCE / "V4_CALIBRATION_PROFILE.json"
MANIFEST_PATH = EVIDENCE / "V4_CORPUS_MANIFEST.json"
RECEIPT_V3 = ROOT / "evidence" / "media-pipeline-adaptive-v3" / "ADAPTIVE_SMOOTHPLUS_V3_R2_RECEIPT.json"


def as_evidence(data: dict) -> CanaryEvidence:
    return CanaryEvidence(
        window_start=float(data["window_start"]),
        window_end=float(data["window_end"]),
        canary_start=float(data["canary_start"]),
        canary_end=float(data["canary_end"]),
        sample_count=int(data["sample_count"]),
        valid_triple_ratio=float(data["valid_triple_ratio"]),
        source_baseline=data.get("source_baseline", {}),
        candidate_metrics=data.get("candidate_metrics", {}),
        robust_z=data.get("robust_z", {}),
        calibration_z=data.get("calibration_z", {}),
        quality_score=float(data.get("quality_score", 0.0)),
        decision=str(data.get("decision", "REVIEW")),
        reasons=tuple(data.get("reasons", ())),
    )
def verify_manifest_sources(manifest: dict) -> list[dict]:
    checks = []
    for sample in manifest["samples"]:
        path = Path(sample["source_path"])
        actual = sha256_file(path)
        checks.append(
            {
                "sample_id": sample["sample_id"],
                "exists": path.exists(),
                "hash_match": actual.lower() == sample["source_sha256"].lower(),
            }
        )
    return checks


def load_single_evidence(name: str) -> CanaryEvidence:
    return as_evidence(json.loads((EVIDENCE / name).read_text(encoding="utf-8")))


def main() -> None:
    profile = load_profile(PROFILE_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_checks = verify_manifest_sources(manifest)
    positive_cases = [
        ("screen-remix-13.json", "screen_remix_real"),
        ("screen-remix-14.json", "screen_remix_real"),
        ("vertical-remaster-13.json", "vertical_remaster_real"),
        ("vertical-remaster-14.json", "vertical_remaster_real"),
    ]
    positives = []
    for name, label in positive_cases:
        scored = score_candidate(load_single_evidence(name), label, profile)
        positives.append(
            {
                "sample": name,
                "class_label": label,
                "expected": "SMOOTH+",
                "actual": scored,
                "pass": scored["decision"] == "SMOOTH+",
            }
        )

    receipt = json.loads(RECEIPT_V3.read_text(encoding="utf-8"))
    rejected = next(
        row for row in receipt["quality_gate"]["canaries"] if row["decision"] == "REVIEW"
    )
    rejected_scored = score_candidate(
        as_evidence(rejected), "screen_mixed_real", profile
    )
    vertical_negative = load_single_evidence("vertical-negative.json")
    negative_cases = [
        {
            "sample": "v3-known-rejected",
            "expected": "REVIEW",
            "actual": rejected_scored,
            "pass": rejected_scored["decision"] == "REVIEW",
        },
        {
            "sample": "vertical-negative",
            "expected": "REVIEW",
            "actual": score_candidate(
                vertical_negative, "vertical_remaster_real", profile
            ),
        },
    ]
    negative_cases[1]["pass"] = negative_cases[1]["actual"]["decision"] == "REVIEW"
    try:
        score_candidate(vertical_negative, "unknown_class", profile)
        unknown_guard = False
    except ValueError:
        unknown_guard = True

    report = {
        "schema": 1,
        "profile_id": profile.profile_id,
        "class_counts": profile.class_counts,
        "source_checks": source_checks,
        "positive_cases": positives,
        "negative_cases": negative_cases,
        "unknown_class_fail_closed": unknown_guard,
        "overall": (
            "PASS"
            if all(x["pass"] for x in positives)
            and all(x["pass"] for x in negative_cases)
            and unknown_guard
            and all(x["exists"] and x["hash_match"] for x in source_checks)
            else "FAIL"
        ),
        "promotion": "DISABLED_REVIEW",
        "limitations": [
            "3 calibration classes",
            "1 unique source file per class",
            "local corpus is screen-oriented",
            "no talking-head source is currently available",
        ],
        "research_basis": [
            "WACV 2025 CLIP-Fusion",
            "ICCV 2025 TLB-VFI",
            "WACV 2025 discontinuous-motion VFI",
        ],
    }
    (EVIDENCE / "V4_VALIDATION_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
