from __future__ import annotations

import json
from pathlib import Path

from scos.media_analysis.adaptive_smooth_plus_v3 import run_quality_canary
from scos.media_analysis.adaptive_smooth_plus_v4 import sha256_file
from scos.media_analysis.source_probe import probe_source

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "media-pipeline-adaptive-v4.1"
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    # Existing V4 source + two genuinely new files.
    ("screen_recording_real", "screen-recording-main", r"C:\Users\chara\OneDrive\Videos\à¸à¸²à¸£à¸šà¸±à¸™à¸—à¸¶à¸à¸«à¸™à¹‰à¸²à¸ˆà¸­\à¸à¸²à¸£à¸šà¸±à¸™à¸—à¸¶à¸à¸«à¸™à¹‰à¸²à¸ˆà¸­ 2026-09-27 091454.mp4"),
    ("screen_recording_real", "screen-desktop", r"C:\Users\chara\Downloads\SCOS_single_screen_desktop.mp4"),
    ("screen_recording_real", "screen-download", r"C:\Users\chara\Downloads\Download.mp4"),

    # Existing V4 source + two genuinely new files.
    ("portrait_visual_real", "portrait-remaster", r"C:\Users\chara\Downloads\Download_single_screen_remix_REMASTERED_1080x1920.mp4"),
    ("portrait_visual_real", "portrait-download-remix", r"C:\Users\chara\Downloads\Download_single_screen_remix.mp4"),
    ("portrait_visual_real", "portrait-phone", r"C:\Users\chara\Downloads\SCOS_single_screen_phone.mp4"),

    # New motion family: natural/animated continuous motion.
    ("portrait_visual_real", "portrait-northern-viking", r"C:\Users\chara\Downloads\scos_calibration_sources\portrait_visual\northern_viking_vertical.mp4"),
    ("natural_motion_real", "natural-elephantsdream", r"C:\Users\chara\Downloads\scos_calibration_sources\elephantsdream\elephantsdream_teaser.mp4"),
    ("natural_motion_real", "natural-internal-preview", r"C:\Users\chara\Downloads\scos_calibration_sources\internalpreview\internal-preview.mp4"),
]


def spans(duration: float) -> list[tuple[float, float]]:
    length = min(1.0, max(0.5, duration * 0.08))
    available = max(0.0, duration - length - 0.25)
    if available <= 0:
        return [(0.0, min(length, duration))]
    starts = [max(0.10, available * 0.20), max(0.10, available * 0.60)]
    return [
        (round(s, 6), round(min(s + length, duration - 0.05), 6))
        for s in starts
    ]


def main() -> None:
    manifest = {
        "schema": 1,
        "purpose": "V4.1 multi-class corpus expansion",
        "source_unit": "unique CFR source file identified by SHA-256",
        "classes": {},
        "samples": [],
    }

    seen_sha: set[str] = set()

    for class_label, sample_id, source in SOURCES:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(source)

        sha = sha256_file(path)
        if sha in seen_sha:
            raise ValueError(f"duplicate source SHA across corpus: {source}")
        seen_sha.add(sha)

        probe = probe_source(path)
        if not probe.cfr:
            raise ValueError(f"V4.1 source must be CFR: {source}")

        class_dir = OUT / class_label
        class_dir.mkdir(parents=True, exist_ok=True)

        for idx, (start, end) in enumerate(spans(float(probe.duration_s)), start=1):
            evidence_path = class_dir / f"{sample_id}-{idx}.json"
            if evidence_path.exists():
                evidence_path.unlink()

            evidence = run_quality_canary(
                path,
                (start, end),
                temp_root=OUT / "tmp" / f"{sample_id}-{idx}",
            )
            evidence_path.write_text(
                json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            manifest["samples"].append(
                {
                    "sample_id": f"{sample_id}-{idx}",
                    "class_label": class_label,
                    "source_path": str(path),
                    "source_sha256": sha,
                    "source_family_id": sha,
                    "canary_index": idx,
                    "window_start": start,
                    "window_end": end,
                    "reference_decision": evidence.decision,
                    "evidence_path": str(evidence_path),
                    "source_probe": {
                        "cfr": probe.cfr,
                        "fps": probe.fps,
                        "duration_s": probe.duration_s,
                        "width": probe.width,
                        "height": probe.height,
                    },
                }
            )

    for label in sorted({x[0] for x in SOURCES}):
        source_hashes = sorted(
            {s["source_sha256"] for s in manifest["samples"] if s["class_label"] == label}
        )
        manifest["classes"][label] = {
            "source_count": len(source_hashes),
            "source_sha256s": source_hashes,
        }

    (OUT / "V4_1_CORPUS_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "classes": {k: v["source_count"] for k, v in manifest["classes"].items()},
        "samples": len(manifest["samples"]),
        "output": str(OUT / "V4_1_CORPUS_MANIFEST.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
