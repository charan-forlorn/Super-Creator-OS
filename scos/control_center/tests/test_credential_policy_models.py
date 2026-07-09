"""Stage 8.3 credential policy model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.credential_policy_models import (
    REDACTION_MARKER,
    STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION,
    CredentialPolicyViolation,
    FrozenPolicyMap,
    create_default_credential_policy,
)

_NOW = "2026-07-10T07:00:00Z"


def test_default_policy_is_immutable_and_deterministic() -> None:
    policy = create_default_credential_policy({"checked_at": _NOW})

    assert policy.schema_version == STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION
    assert policy.redaction_marker == REDACTION_MARKER
    assert policy.to_dict() == policy.to_dict()
    assert "SNAPSHOT" in policy.forbidden_output_surfaces
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "changed"  # type: ignore[misc]


def test_nested_policy_metadata_is_frozen_on_input() -> None:
    metadata = {"nested": {"items": ["a", "b"]}}
    frozen = FrozenPolicyMap.from_mapping(metadata)
    metadata["nested"]["items"].append("c")

    assert frozen.to_dict() == {"nested": {"items": ["a", "b"]}}
    with pytest.raises(FrozenInstanceError):
        frozen.items = ()  # type: ignore[misc]


def test_policy_sorts_markers_and_locations() -> None:
    policy = create_default_credential_policy()
    payload = policy.to_dict()

    assert payload["secret_field_markers"] == sorted(payload["secret_field_markers"])
    assert payload["allowed_local_evidence_locations"] == sorted(payload["allowed_local_evidence_locations"])


def test_violation_rejects_unknown_surface_category_and_severity() -> None:
    with pytest.raises(ValueError):
        CredentialPolicyViolation(
            violation_id="v1",
            surface="REMOTE",
            path="$",
            category="TOKEN",
            severity="SECRET",
            message="bad",
            evidence="***",
        )
    with pytest.raises(ValueError):
        CredentialPolicyViolation(
            violation_id="v1",
            surface="LOG",
            path="$",
            category="REMOTE_SECRET",
            severity="SECRET",
            message="bad",
            evidence="***",
        )
    with pytest.raises(ValueError):
        CredentialPolicyViolation(
            violation_id="v1",
            surface="LOG",
            path="$",
            category="TOKEN",
            severity="CRITICAL",
            message="bad",
            evidence="***",
        )
