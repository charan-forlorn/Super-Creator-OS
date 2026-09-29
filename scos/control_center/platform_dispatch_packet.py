"""Deterministic outbound dispatch packet; governance handoff only.

The packet is a serialized request for a future governed connector. It never
contacts Buffer/platform APIs, reads secrets, or publishes. A connector may only
consume it after the HAIOS governance layer establishes authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from scos.control_center.platform_delivery_plan import PlatformDeliveryPlan

SUPPORTED_CONNECTORS = frozenset({"buffer"})
STATE_READY_FOR_GOVERNED_DISPATCH = "READY_FOR_GOVERNED_DISPATCH"


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlatformDispatchPacket:
    schema_version: int
    request_id: str
    connector: str
    plan_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    account_reference: str
    publish_at: str | None
    title: str
    caption: str
    hashtags: tuple[str, ...]
    variants: tuple[dict[str, Any], ...]
    state: str
    external_dispatch_allowed: bool
    human_approval_required: bool
    secret_material_included: bool
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "connector": self.connector,
            "plan_id": self.plan_id,
            "source_artifact_id": self.source_artifact_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "account_reference": self.account_reference,
            "publish_at": self.publish_at,
            "title": self.title,
            "caption": self.caption,
            "hashtags": list(self.hashtags),
            "variants": list(self.variants),
            "state": self.state,
            "external_dispatch_allowed": self.external_dispatch_allowed,
            "human_approval_required": self.human_approval_required,
            "secret_material_included": self.secret_material_included,
            "content_hash": self.content_hash,
        }


def build_dispatch_packet(
    plan: PlatformDeliveryPlan,
    *,
    connector: str,
    account_reference: str,
    publish_at: str | None = None,
) -> PlatformDispatchPacket:
    connector = connector.strip().lower()
    if connector not in SUPPORTED_CONNECTORS:
        raise ValueError(f"unsupported dispatch connector: {connector!r}")
    if not account_reference.strip():
        raise ValueError("account_reference is required")
    if plan.state != "READY_FOR_MANUAL_PUBLISH":
        raise ValueError("delivery plan is not ready for dispatch packet creation")

    payload = {
        "schema_version": 1,
        "connector": connector,
        "plan_id": plan.plan_id,
        "source_artifact_id": plan.source_artifact_id,
        "source_artifact_sha256": plan.source_artifact_sha256,
        "account_reference": account_reference.strip(),
        "publish_at": publish_at,
        "title": plan.title,
        "caption": plan.caption,
        "hashtags": list(plan.hashtags),
        "variants": [variant.to_dict() for variant in plan.variants],
    }
    content_hash = _hash(payload)
    return PlatformDispatchPacket(
        schema_version=1,
        request_id=f"scos-dispatch-{content_hash[:16]}",
        connector=connector,
        plan_id=plan.plan_id,
        source_artifact_id=plan.source_artifact_id,
        source_artifact_sha256=plan.source_artifact_sha256,
        account_reference=account_reference.strip(),
        publish_at=publish_at,
        title=plan.title,
        caption=plan.caption,
        hashtags=plan.hashtags,
        variants=tuple(variant.to_dict() for variant in plan.variants),
        state=STATE_READY_FOR_GOVERNED_DISPATCH,
        external_dispatch_allowed=False,
        human_approval_required=True,
        secret_material_included=False,
        content_hash=content_hash,
    )


__all__ = [
    "PlatformDispatchPacket",
    "STATE_READY_FOR_GOVERNED_DISPATCH",
    "SUPPORTED_CONNECTORS",
    "build_dispatch_packet",
]
