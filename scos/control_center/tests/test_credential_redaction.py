"""Stage 8.3 credential redaction tests."""

from __future__ import annotations

from copy import deepcopy

from scos.control_center.credential_policy_models import REDACTION_MARKER
from scos.control_center.credential_redaction import (
    classify_secret_field_name,
    classify_secret_value,
    redact_credential_payload,
)


def _fake_secret() -> str:
    return "FAKE_" + "SECRET" + "_DO_NOT_USE"


def test_secret_field_names_are_redacted_without_mutating_input() -> None:
    key = "api" + "_key"
    payload = {
        "service": "manual",
        key: _fake_secret(),
        "nested": {"authorization_header": "Bearer fakeheader"},
    }
    original = deepcopy(payload)

    result = redact_credential_payload(payload)

    assert result.accepted is True
    assert payload == original
    assert result.to_dict()["redacted_payload"][key] == REDACTION_MARKER
    assert result.to_dict()["redacted_payload"]["nested"]["authorization_header"] == REDACTION_MARKER
    assert len(result.findings) == 2


def test_secret_like_values_are_redacted_inside_lists() -> None:
    payload = {"events": ["safe", _fake_secret(), {"message": "Bearer synthetictoken"}]}

    result = redact_credential_payload(payload)
    redacted = result.to_dict()["redacted_payload"]

    assert redacted["events"][0] == "safe"
    assert redacted["events"][1] == REDACTION_MARKER
    assert redacted["events"][2]["message"] == REDACTION_MARKER
    assert [finding.path for finding in result.findings] == sorted(finding.path for finding in result.findings)


def test_classifiers_detect_field_and_value_markers() -> None:
    assert classify_secret_field_name("operator_token_ref") == "TOKEN"
    assert classify_secret_field_name("caption_style") is None
    assert classify_secret_value(_fake_secret()) == "GENERIC_SECRET"
    assert classify_secret_value("safe audit metadata") is None
