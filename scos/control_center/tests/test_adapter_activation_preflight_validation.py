"""Stage 7.7 adapter activation preflight validation tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.adapter_activation_preflight_validation import (
    validate_adapter_activation_preflight_inputs,
    validate_no_secret_or_remote_text,
    validate_output_path,
    validate_repo_root,
)

_NOW = "2026-07-10T02:00:00Z"


def test_checked_at_is_required_and_caller_supplied(tmp_path: Path) -> None:
    _root, _out, error = validate_adapter_activation_preflight_inputs(
        repo_root=tmp_path,
        checked_at="",
    )

    assert error is not None
    assert error.error_code == "INVALID_ADAPTER_PREFLIGHT_INPUT"
    assert "checked_at must be caller-supplied" in error.blockers[0]


def test_target_adapter_and_mode_validation(tmp_path: Path) -> None:
    _root, _out, bad_adapter = validate_adapter_activation_preflight_inputs(
        repo_root=tmp_path,
        checked_at=_NOW,
        target_adapter="bad",
    )
    _root, _out, bad_mode = validate_adapter_activation_preflight_inputs(
        repo_root=tmp_path,
        checked_at=_NOW,
        requested_activation_mode="real_dispatch",
    )

    assert bad_adapter is not None
    assert any("target_adapter" in blocker for blocker in bad_adapter.blockers)
    assert bad_mode is not None
    assert any("forbidden" in blocker for blocker in bad_mode.blockers)


def test_secret_and_remote_text_are_rejected() -> None:
    assert validate_no_secret_or_remote_text("field", "https://example.com")
    assert validate_no_secret_or_remote_text("field", "OPENAI_API_KEY=value")


def test_repo_root_and_output_path_must_be_local_and_contained(tmp_path: Path) -> None:
    root, errors = validate_repo_root(tmp_path)
    assert root == tmp_path.resolve()
    assert errors == ()

    output, output_errors = validate_output_path(tmp_path.resolve(), "reports/preflight.json")
    assert output == (tmp_path / "reports/preflight.json").resolve()
    assert output_errors == ()

    escaped, escaped_errors = validate_output_path(tmp_path.resolve(), tmp_path.parent / "outside.json")
    assert escaped is None
    assert "output_path must resolve inside repo_root" in escaped_errors
