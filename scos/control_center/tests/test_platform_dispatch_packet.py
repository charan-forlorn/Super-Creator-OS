from __future__ import annotations

import pytest

from scos.control_center.platform_delivery_plan import BrandPresentationSpec, build_platform_delivery_plan
from scos.control_center.platform_dispatch_packet import (
    STATE_READY_FOR_GOVERNED_DISPATCH,
    build_dispatch_packet,
)

_SHA = "a" * 64
_BRAND = BrandPresentationSpec("brand-demo", "logo-1", "#111111", "#00A0A0", "Inter", "concise")


def _plan():
    return build_platform_delivery_plan(
        source_artifact_id="artifact-1",
        source_artifact_sha256=_SHA,
        brand=_BRAND,
        format_ids=("vertical_9_16",),
        title="Launch",
        caption="Launch caption",
        hashtags=("#launch",),
    )


def test_dispatch_packet_is_deterministic_and_secret_free() -> None:
    plan = _plan()
    a = build_dispatch_packet(
        plan, connector="buffer", account_reference="buffer-account-ref", publish_at="2026-09-20T12:00:00Z"
    )
    b = build_dispatch_packet(
        plan, connector="buffer", account_reference="buffer-account-ref", publish_at="2026-09-20T12:00:00Z"
    )
    assert a.request_id == b.request_id
    assert a.content_hash == b.content_hash
    assert a.state == STATE_READY_FOR_GOVERNED_DISPATCH
    assert a.external_dispatch_allowed is False
    assert a.human_approval_required is True
    assert a.secret_material_included is False
    assert "API_KEY" not in str(a.to_dict()).upper()


def test_connector_and_account_are_explicit() -> None:
    packet = build_dispatch_packet(_plan(), connector="BUFFER", account_reference="acct-1")
    assert packet.connector == "buffer"
    assert packet.account_reference == "acct-1"


def test_invalid_connector_or_non_ready_plan_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported dispatch connector"):
        build_dispatch_packet(_plan(), connector="tiktok-direct", account_reference="acct")
    blocked = build_platform_delivery_plan(
        source_artifact_id="",
        source_artifact_sha256="bad",
        brand=_BRAND,
        format_ids=("vertical_9_16",),
        title="",
        caption="",
    )
    with pytest.raises(ValueError, match="delivery plan is not ready"):
        build_dispatch_packet(blocked, connector="buffer", account_reference="acct")
