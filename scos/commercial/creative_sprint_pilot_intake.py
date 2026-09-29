"""Bridge a verified Creative Sprint offer into a manual paid-pilot intake starter.

The starter is a customer/operator input contract. It never admits a pilot,
creates customer records, processes payment, accesses external accounts, or
fills rights/consent/privacy answers on behalf of a customer.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATE_READY_FOR_CUSTOMER_INPUT = "READY_FOR_CUSTOMER_INPUT"
STATE_BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CreativeSprintPilotIntakeStarter:
    ok: bool
    state: str
    starter_id: str
    offer_id: str
    offer_name: str
    price: str
    variant_count: int
    offer_manifest_path: str
    starter_manifest_path: str
    required_customer_inputs: tuple[str, ...]
    external_actions_locked: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": self.ok,
            "state": self.state,
            "starter_id": self.starter_id,
            "offer_id": self.offer_id,
            "offer_name": self.offer_name,
            "price": self.price,
            "variant_count": self.variant_count,
            "offer_manifest_path": self.offer_manifest_path,
            "starter_manifest_path": self.starter_manifest_path,
            "required_customer_inputs": list(self.required_customer_inputs),
            "external_actions_locked": self.external_actions_locked,
        }


_REQUIRED_INPUTS = (
    "customer_reference",
    "project_title",
    "business_or_offer_context",
    "target_audience",
    "primary_message",
    "call_to_action",
    "target_channel",
    "deadline",
    "approved_assets",
    "asset_rights_declarations",
    "privacy_answers",
    "explicit_customer_consent_evidence",
    "revision_notes",
)


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("offer manifest must be a JSON object")
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_creative_sprint_pilot_intake(
    *,
    offer_manifest_path: str | Path,
    output_dir: str | Path | None = None,
) -> CreativeSprintPilotIntakeStarter:
    offer_path = Path(offer_manifest_path).resolve()
    if not offer_path.is_file():
        raise FileNotFoundError(f"offer manifest not found: {offer_path}")

    offer = _load(offer_path)
    if offer.get("state") not in (None, "READY_FOR_MANUAL_OFFER"):
        raise ValueError("offer is not ready for manual offering")
    if offer.get("creative_qa_status") != "PASS":
        raise ValueError("offer does not reference a passing creative QA state")
    if int(offer.get("variant_count", 0)) < 3:
        raise ValueError("offer must contain at least three verified variants")
    if offer.get("external_dispatch_allowed") is not False:
        raise ValueError("external dispatch must remain disabled")
    if offer.get("manual_publish_required") is not True:
        raise ValueError("manual publish must remain required")

    digest = hashlib.sha256(
        json.dumps(
            {
                "offer_id": offer.get("offer_id"),
                "source_artifact_sha256": offer.get("source_artifact_sha256"),
                "required_customer_inputs": _REQUIRED_INPUTS,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    starter_id = f"pilot-intake-{digest[:16]}"

    out = (
        Path(output_dir).resolve()
        if output_dir is not None
        else offer_path.parent / "pilot_intake"
    )
    offer_root = offer_path.parent.resolve()
    out.relative_to(offer_root)
    out.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "starter_id": starter_id,
        "state": STATE_READY_FOR_CUSTOMER_INPUT,
        "offer": {
            "offer_id": offer.get("offer_id"),
            "offer_name": offer.get("offer_name"),
            "price": offer.get("price"),
            "delivery_window": offer.get("delivery_window"),
            "variant_count": offer.get("variant_count"),
            "source_artifact_sha256": offer.get("source_artifact_sha256"),
            "performance_claims_allowed": False,
        },
        "required_customer_inputs": list(_REQUIRED_INPUTS),
        "customer_fields": {
            "customer_reference": "",
            "project_title": "",
            "business_or_offer_context": "",
            "target_audience": "",
            "primary_message": "",
            "call_to_action": "",
            "target_channel": "",
            "deadline": "",
            "revision_notes": "",
        },
        "approval_fields": {
            "approved_assets": [],
            "asset_rights_declarations": {},
            "privacy_answers": {},
            "explicit_customer_consent_evidence": None,
        },
        "locked_actions": {
            "customer_notification": "NOT_AUTHORIZED",
            "external_delivery": "NOT_AUTHORIZED",
            "publishing": "NOT_AUTHORIZED",
            "upload": "NOT_AUTHORIZED",
            "deployment": "NOT_AUTHORIZED",
        },
        "next_action": "Collect and verify customer inputs, then use the authoritative Guided Pilot Intake.",
        "authority_note": "This starter is not a pilot admission record and does not authorize rendering or external delivery.",
        "source_offer_sha256": _sha256(offer_path),
    }

    manifest = out / "pilot_intake_starter.json"
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    form = out / "customer_intake_form.md"
    form.write_text(
        "# Creative Sprint — Paid Pilot Intake\n\n"
        "This form collects customer inputs for manual review. Completing it does not authorize payment, publication, upload, or external delivery.\n\n"
        "## Customer / Project\n"
        + "\n".join(f"- **{field}:** ____________________" for field in _REQUIRED_INPUTS[:8])
        + "\n\n## Assets / Rights / Privacy\n"
        + "\n".join(f"- **{field}:** ____________________" for field in _REQUIRED_INPUTS[8:])
        + "\n\n## Commercial terms\n"
        + f"- Offer: {offer.get('offer_name')}\n"
        + f"- Price: {offer.get('price')}\n"
        + f"- Delivery target: {offer.get('delivery_window')}\n"
        + "- Included revision rounds: 1\n"
        + "\n## Manual gates\n"
        "- [ ] Scope confirmed\n"
        "- [ ] Customer assets verified\n"
        "- [ ] Rights/privacy confirmed\n"
        "- [ ] Explicit customer consent evidence received\n"
        "- [ ] Payment/price confirmation handled manually\n"
        "- [ ] Guided Pilot Intake validation passes\n"
        "- [ ] Human approval before any render/delivery action\n",
        encoding="utf-8",
    )

    return CreativeSprintPilotIntakeStarter(
        ok=True,
        state=STATE_READY_FOR_CUSTOMER_INPUT,
        starter_id=starter_id,
        offer_id=str(offer.get("offer_id") or ""),
        offer_name=str(offer.get("offer_name") or ""),
        price=str(offer.get("price") or ""),
        variant_count=int(offer.get("variant_count") or 0),
        offer_manifest_path=str(offer_path),
        starter_manifest_path=str(manifest),
        required_customer_inputs=_REQUIRED_INPUTS,
        external_actions_locked=True,
    )


__all__ = (
    "CreativeSprintPilotIntakeStarter",
    "STATE_READY_FOR_CUSTOMER_INPUT",
    "build_creative_sprint_pilot_intake",
)
