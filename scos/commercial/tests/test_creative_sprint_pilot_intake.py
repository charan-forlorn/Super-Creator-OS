from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.commercial.creative_sprint_pilot_intake import (
    STATE_READY_FOR_CUSTOMER_INPUT,
    build_creative_sprint_pilot_intake,
)


def _offer(tmp_path: Path, **overrides):
    data = {
        "state": "READY_FOR_MANUAL_OFFER",
        "offer_id": "creative-sprint-test",
        "offer_name": "Performance Creative Production Sprint",
        "price": "9900 THB",
        "delivery_window": "48-72 hours",
        "variant_count": 3,
        "creative_qa_status": "PASS",
        "external_dispatch_allowed": False,
        "manual_publish_required": True,
        "source_artifact_sha256": "a" * 64,
    }
    data.update(overrides)
    path = tmp_path / "creative_sprint_offer.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_build_starter(tmp_path: Path):
    offer = _offer(tmp_path)
    result = build_creative_sprint_pilot_intake(offer_manifest_path=offer)
    assert result.ok is True
    assert result.state == STATE_READY_FOR_CUSTOMER_INPUT
    assert result.external_actions_locked is True
    starter = Path(result.starter_manifest_path)
    assert starter.is_file()
    data = json.loads(starter.read_text(encoding="utf-8"))
    assert data["locked_actions"]["publishing"] == "NOT_AUTHORIZED"
    assert data["customer_fields"]["customer_reference"] == ""
    assert len(data["required_customer_inputs"]) == 13


def test_starter_is_reproducible_for_same_offer(tmp_path: Path):
    offer = _offer(tmp_path)
    a = build_creative_sprint_pilot_intake(offer_manifest_path=offer)
    b = build_creative_sprint_pilot_intake(offer_manifest_path=offer)
    assert a.starter_id == b.starter_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"creative_qa_status": "FAIL"},
        {"variant_count": 2},
        {"external_dispatch_allowed": True},
        {"manual_publish_required": False},
    ],
)
def test_unsafe_offer_is_rejected(tmp_path: Path, overrides):
    offer = _offer(tmp_path, **overrides)
    with pytest.raises(ValueError):
        build_creative_sprint_pilot_intake(offer_manifest_path=offer)


def test_output_must_stay_under_offer_root(tmp_path: Path):
    offer = _offer(tmp_path)
    with pytest.raises(ValueError):
        build_creative_sprint_pilot_intake(
            offer_manifest_path=offer,
            output_dir=tmp_path.parent / "escape",
        )
