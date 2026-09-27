from pathlib import Path
import sys

ROOT = Path(r"C:/Workspace/super-creator-os")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_smoothplus_v4_1 import main

if __name__ == "__main__":
    main()

def load_evidence(path: Path) -> CanaryEvidence:
    d = json.loads(path.read_text(encoding="utf-8-sig"))
    return CanaryEvidence(
        window_start=float(d["window_start"]),
        window_end=float(d["window_end"]),
        canary_start=float(d["canary_start"]),
        canary_end=float(d["canary_end"]),
        sample_count=int(d["sample_count"]),
        valid_triple_ratio=float(d["valid_triple_ratio"]),
        source_baseline=d.get("source_baseline", {}),
        candidate_metrics=d.get("candidate_metrics", {}),
        robust_z=d.get("robust_z", {}),
        calibration_z=d.get("calibration_z", {}),
        quality_score=float(d.get("quality_score", 0.0)),
        decision=str(d.get("decision", "REVIEW")),
        reasons=tuple(d.get("reasons", ())),
    )

manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
samples = manifest["samples"]
by_source = defaultdict(list)
for s in samples:
    by_source[s["source_family_id"]].append(s)

assert len(by_source) == 9, f"expected 9 unique sources, got {len(by_source)}"
source_meta = {}
for sid, rows in by_source.items():
    paths = {Path(r["source_path"]) for r in rows}
    shas = {r["source_sha256"].lower() for r in rows}
    assert len(paths) == 1 and len(shas) == 1, f"source identity inconsistent: {sid}"
    path = next(iter(paths))
    assert path.exists(), f"missing source: {path}"
    actual = sha256_file(path).lower()
    assert actual == next(iter(shas)), f"hash mismatch: {path}"
    source_meta[sid] = {"class_label": rows[0]["class_label"], "path": str(path), "sha256": actual}

folds = []
global_counts = defaultdict(int)
for heldout_sid, heldout_rows in sorted(by_source.items()):
    train_rows = [s for sid, rs in by_source.items() if sid != heldout_sid for s in rs]
    train_sids = {s["source_family_id"] for s in train_rows}
    assert heldout_sid not in train_sids

    train_samples = [
        CalibrationSample(
            sample_id=s["sample_id"],
            class_label=s["class_label"],
            source_path=s["source_path"],
            source_sha256=s["source_sha256"],
            evidence_path=s["evidence_path"],
            candidate_count=1,
        )
        for s in train_rows
    ]
    profile = build_calibration_profile(train_samples, min_samples_per_class=2)

    predictions = []
    for s in heldout_rows:
        ev = load_evidence(Path(s["evidence_path"]))
        scored = score_candidate(ev, s["class_label"], profile)
        ref = s["reference_decision"]
        pred = scored["decision"]
        agreement = pred == ref
        false_accept = pred == "SMOOTH+" and ref == "REVIEW"
        false_reject = pred == "REVIEW" and ref == "SMOOTH+"
        predictions.append({
            "sample_id": s["sample_id"],
            "class_label": s["class_label"],
            "reference_decision": ref,
            "predicted_decision": pred,
            "agreement": agreement,
            "false_accept": false_accept,
            "false_reject": false_reject,
            "worst_z": scored["worst_z"],
            "mean_z": scored["mean_z"],
            "quality_score": scored["quality_score"],
            "reasons": scored["reasons"],
        })
        global_counts["tests"] += 1
        global_counts["agreements"] += int(agreement)
        global_counts["false_accepts"] += int(false_accept)
        global_counts["false_rejects"] += int(false_reject)

    folds.append({
        "held_out_source_family_id": heldout_sid,
        "held_out_class": source_meta[heldout_sid]["class_label"],
        "held_out_source_path": source_meta[heldout_sid]["path"],
        "held_out_source_sha256": source_meta[heldout_sid]["sha256"],
        "training_source_family_count": len(train_sids),
        "training_source_family_ids": sorted(train_sids),
        "profile_id": profile.profile_id,
        "source_leakage": heldout_sid in train_sids,
        "predictions": predictions,
    })

classes = defaultdict(list)
for sid, meta in source_meta.items():
    classes[meta["class_label"]].append(sid)

report = {
    "schema": 1,
    "validation": "leave_one_source_out",
    "corpus_manifest": str(MANIFEST),
    "unique_source_count": len(by_source),
    "class_source_counts": {k: len(v) for k, v in sorted(classes.items())},
    "source_hash_verification": "PASS",
    "source_level_leakage": any(f["source_leakage"] for f in folds),
    "fold_count": len(folds),
    "test_count": global_counts["tests"],
    "agreement_count": global_counts["agreements"],
    "agreement_rate": global_counts["agreements"] / max(1, global_counts["tests"]),
    "false_accept_count": global_counts["false_accepts"],
    "false_reject_count": global_counts["false_rejects"],
    "safety_status": "PASS" if global_counts["false_accepts"] == 0 and not report_source_leakage(folds) else "REVIEW",
    "policy_note": "reference_decision is V3 deterministic policy output, not human perceptual ground truth",
    "folds": folds,
    "class_results": {},
    "limitations": [
        "The current corpus has three unique sources per class.",
        "The reference labels are V3 canary decisions, not independent human ground truth.",
        "natural_motion_real mixes 24fps animation sources with a 10fps internal preview.",
    ],
}

def report_source_leakage(fs):
    return any(f["source_leakage"] for f in fs)

for cls, source_ids in sorted(classes.items()):
    preds = [p for f in folds if f["held_out_class"] == cls for p in f["predictions"]]
    tests = len(preds)
    agreements = sum(p["agreement"] for p in preds)
    fas = sum(p["false_accept"] for p in preds)
    frs = sum(p["false_reject"] for p in preds)
    report["class_results"][cls] = {
        "source_count": len(source_ids),
        "test_count": tests,
        "agreement_rate": agreements / max(1, tests),
        "false_accept_count": fas,
        "false_reject_count": frs,
    }

report["overall"] = "PASS" if (
    report["fold_count"] == 9
    and report["test_count"] == 18
    and not report["source_level_leakage"]
    and report["false_accept_count"] == 0
) else "REVIEW"

out = EV / "V4_1_LOSO_VALIDATION_REPORT.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "overall": report["overall"],
    "folds": report["fold_count"],
    "tests": report["test_count"],
    "agreement_rate": report["agreement_rate"],
    "false_accepts": report["false_accept_count"],
    "false_rejects": report["false_reject_count"],
    "class_results": report["class_results"],
}, ensure_ascii=False, indent=2))
