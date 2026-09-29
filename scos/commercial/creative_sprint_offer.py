"""Deterministic commercial packaging for one SCOS Creative Sprint.

Thin adapter over already-verified production artifacts. It does not publish,
contact customers, process payments, or claim performance outcomes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
OFFER_NAME = "Performance Creative Production Sprint"
DEFAULT_PRICE = "9900 THB"
DEFAULT_DELIVERY_WINDOW = "48-72 hours target after complete inputs"


@dataclass(frozen=True)
class CreativeSprintOffer:
    ok: bool
    offer_id: str
    state: str
    production_root: str
    output_dir: str
    source_artifact_sha256: str
    variant_count: int
    price: str
    delivery_window: str
    performance_claims_allowed: bool
    manifest_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": self.ok,
            "offer_id": self.offer_id,
            "state": self.state,
            "production_root": self.production_root,
            "output_dir": self.output_dir,
            "source_artifact_sha256": self.source_artifact_sha256,
            "variant_count": self.variant_count,
            "price": self.price,
            "delivery_window": self.delivery_window,
            "performance_claims_allowed": self.performance_claims_allowed,
            "manifest_path": self.manifest_path,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _safe_child(root: Path, child: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved_child = child.resolve()
    resolved_child.relative_to(resolved_root)
    return resolved_child

def _markdown_offer(data: dict[str, Any]) -> str:
    variants = data["variants"]
    lines = [
        f"# {OFFER_NAME}",
        "",
        "## What the customer receives",
        "- 1 short-form creative concept and production.",
        f"- {data['variant_count']} delivery formats: " + ", ".join(v["format_id"] for v in variants) + ".",
        "- Technical QA and artifact verification.",
        "- Commercial asset/license audit based on production evidence.",
        "- 1 revision round.",
        "",
        "## Price",
        data["price"],
        "",
        "## Target delivery window",
        data["delivery_window"],
        "",
        "## Not included",
        "- Media buying or ad-spend management.",
        "- Automatic publishing or account access.",
        "- Guaranteed views, leads, sales, ROAS, or other performance outcomes.",
        "- Automatic external dispatch.",
        "",
        "## Current evidence",
        f"- Source artifact SHA-256: {data['source_artifact_sha256']}",
        f"- Production-loop status: {data['production_loop_status']}",
        f"- Creative QA: {data['creative_qa_status']}",
        "",
        "## Next manual step",
        "Confirm scope, inputs, price, and delivery date with the customer before accepting the job.",
        "",
    ]
    return "\n".join(lines)


def _markdown_checklist() -> str:
    return """# Customer Review Checklist

- [ ] Scope and objective confirmed.
- [ ] Brand assets and source media supplied.
- [ ] Offer price confirmed.
- [ ] Delivery date confirmed.
- [ ] Customer approves creative direction before final delivery.
- [ ] Any requested revision is within the included revision round.
- [ ] Human verifies final files before sending.
- [ ] Human publishes manually; SCOS does not auto-publish.
- [ ] No performance result is claimed without observed telemetry.
"""


def build_creative_sprint_offer(
    *,
    production_root: str | Path,
    output_dir: str | Path | None = None,
    price: str = DEFAULT_PRICE,
    delivery_window: str = DEFAULT_DELIVERY_WINDOW,
    copy_artifacts: bool = True,
) -> CreativeSprintOffer:
    root = Path(production_root)
    manifest_path = root / "manifest.json"
    qa_path = root / "qa" / "qa_report.json"
    receipt_path = root / "evidence" / "production_loop_receipt.json"
    if not manifest_path.is_file() or not qa_path.is_file() or not receipt_path.is_file():
        raise FileNotFoundError("production run is missing manifest, QA report, or production-loop receipt")

    manifest = _load_json(manifest_path)
    qa = _load_json(qa_path)
    receipt = _load_json(receipt_path)
    if qa.get("overall_pass") is not True:
        raise ValueError("creative QA is not PASS")
    if manifest.get("technical_qa") != "PASS":
        raise ValueError("technical QA is not PASS")

    # QA report is the authoritative source for verified variant paths/status.
    variants = qa.get("variants") or manifest.get("variants")
    if not isinstance(variants, list) or len(variants) < 3:
        raise ValueError("at least three verified platform variants are required")
    verified_variants: list[dict[str, Any]] = []
    for variant in variants:
        path = Path(str(variant.get("path") or ""))
        if not path.is_absolute():
            path = (root.parent.parent.parent / path).resolve()
        if not path.is_file() or variant.get("qa_pass") is not True:
            raise ValueError(f"variant is missing or failed QA: {variant.get('format_id')}")
        verified_variants.append({
            "format_id": variant.get("format_id"),
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "width": variant.get("width"),
            "height": variant.get("height"),
            "duration_s": variant.get("duration_s"),
        })

    restricted = set(qa.get("external_assets_license_audit", {}).get("restricted_use_only") or ())
    used = set(manifest.get("external_assets_used") or ())
    if restricted & used:
        raise ValueError("restricted-use asset is listed in final production manifest")

    artifact_sha = str(manifest.get("final_sha256") or "")
    if len(artifact_sha) != 64:
        output_path = Path(str(manifest.get("output", {}).get("path") or ""))
        if output_path.is_file():
            artifact_sha = _sha256(output_path)
        else:
            artifact_sha = verified_variants[0]["sha256"]

    loop_status = str(receipt.get("status") or "UNKNOWN")
    telemetry_status = str(receipt.get("telemetry", {}).get("status") or "UNKNOWN")
    performance_claims_allowed = telemetry_status not in {
        "OPEN_TELEMETRY_DATA_GATE",
        "NO_EXTERNAL_OBSERVATION_EXPORT",
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "offer_name": OFFER_NAME,
        "price": str(price),
        "delivery_window": str(delivery_window),
        "source_artifact_sha256": artifact_sha,
        "variant_count": len(verified_variants),
        "variants": verified_variants,
        "production_loop_status": loop_status,
        "telemetry_status": telemetry_status,
        "performance_claims_allowed": performance_claims_allowed,
        "creative_qa_status": "PASS",
        "included_revision_rounds": 1,
        "manual_publish_required": True,
        "external_dispatch_allowed": False,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    offer_id = f"creative-sprint-{digest[:16]}"

    out = Path(output_dir) if output_dir is not None else root / "commercial_offer"
    out = _safe_child(root, out)
    out.mkdir(parents=True, exist_ok=True)

    artifacts_dir = out / "deliverables"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if copy_artifacts:
        for variant in verified_variants:
            target = artifacts_dir / Path(variant["path"]).name
            shutil.copy2(variant["path"], target)
            copied.append(str(target))

    payload["offer_id"] = offer_id
    payload["production_root"] = str(root.resolve())
    payload["copied_artifacts"] = copied
    payload["claims_note"] = (
        "Performance outcomes require real observed telemetry; this offer is "
        "production-ready, not performance-proven."
    )

    manifest_out = out / "creative_sprint_offer.json"
    manifest_out.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "offer_one_pager.md").write_text(
        _markdown_offer(payload), encoding="utf-8"
    )
    (out / "customer_review_checklist.md").write_text(
        _markdown_checklist(), encoding="utf-8"
    )

    return CreativeSprintOffer(
        ok=True,
        offer_id=offer_id,
        state="READY_FOR_MANUAL_OFFER",
        production_root=str(root.resolve()),
        output_dir=str(out),
        source_artifact_sha256=artifact_sha,
        variant_count=len(verified_variants),
        price=str(price),
        delivery_window=str(delivery_window),
        performance_claims_allowed=performance_claims_allowed,
        manifest_path=str(manifest_out),
    )


__all__ = ("CreativeSprintOffer", "build_creative_sprint_offer")
