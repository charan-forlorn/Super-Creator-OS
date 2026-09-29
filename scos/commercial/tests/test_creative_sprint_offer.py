from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.commercial.creative_sprint_offer import (
    DEFAULT_PRICE,
    build_creative_sprint_offer,
)


def _make_run(root: Path, *, restricted_used: bool = False, qa_pass: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    renders = root / "renders"
    variants_dir = root / "variants"
    qa_dir = root / "qa"
    evidence_dir = root / "evidence"
    for directory in (renders, variants_dir, qa_dir, evidence_dir):
        directory.mkdir(parents=True, exist_ok=True)

    main = renders / "final.mp4"
    main.write_bytes(b"final-video")
    variants = []
    for fmt, name in (
        ("vertical_9_16", "vertical.mp4"),
        ("square_1_1", "square.mp4"),
        ("landscape_16_9", "landscape.mp4"),
    ):
        target = variants_dir / name
        target.write_bytes(fmt.encode())
        variants.append({
            "format_id": fmt,
            "path": str(target),
            "qa_pass": qa_pass,
            "width": 1080,
            "height": 1920 if fmt == "vertical_9_16" else 1080,
            "duration_s": 20.0,
        })

    used = ["restricted.mp4"] if restricted_used else []
    manifest = {
        "technical_qa": "PASS" if qa_pass else "FAIL",
        "final_sha256": "a" * 64,
        "output": {"path": str(main)},
        "variants": variants,
        "external_assets_used": used,
    }
    qa = {
        "overall_pass": qa_pass,
        "variants": variants,
        "external_assets_license_audit": {
            "restricted_use_only": ["restricted.mp4"],
        },
    }
    receipt = {
        "status": "SEALED_WITH_OPEN_TELEMETRY",
        "telemetry": {"status": "OPEN_TELEMETRY_DATA_GATE"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (qa_dir / "qa_report.json").write_text(json.dumps(qa), encoding="utf-8")
    (evidence_dir / "production_loop_receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    return root


def test_build_offer_ready(tmp_path: Path):
    root = _make_run(tmp_path / "run")
    result = build_creative_sprint_offer(production_root=root)
    assert result.ok is True
    assert result.state == "READY_FOR_MANUAL_OFFER"
    assert result.variant_count == 3
    assert result.price == DEFAULT_PRICE
    assert result.performance_claims_allowed is False
    assert Path(result.manifest_path).is_file()
    assert (Path(result.output_dir) / "offer_one_pager.md").is_file()
    assert (Path(result.output_dir) / "customer_review_checklist.md").is_file()


def test_offer_copies_three_variants(tmp_path: Path):
    root = _make_run(tmp_path / "run")
    result = build_creative_sprint_offer(production_root=root)
    copied = list((Path(result.output_dir) / "deliverables").glob("*.mp4"))
    assert len(copied) == 3


def test_restricted_asset_blocks_offer(tmp_path: Path):
    root = _make_run(tmp_path / "run", restricted_used=True)
    with pytest.raises(ValueError, match="restricted-use asset"):
        build_creative_sprint_offer(production_root=root)


def test_failed_qa_blocks_offer(tmp_path: Path):
    root = _make_run(tmp_path / "run", qa_pass=False)
    with pytest.raises(ValueError, match="creative QA"):
        build_creative_sprint_offer(production_root=root)


def test_offer_is_not_performance_proven_without_telemetry(tmp_path: Path):
    root = _make_run(tmp_path / "run")
    result = build_creative_sprint_offer(production_root=root)
    data = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert data["performance_claims_allowed"] is False
    assert data["external_dispatch_allowed"] is False
    assert data["manual_publish_required"] is True
