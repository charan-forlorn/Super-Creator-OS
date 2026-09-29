from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from integrations.learning.youtube_oauth_store import (
    credential_exists,
    load_credential,
    save_credential,
)


def test_dpapi_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "youtube.dpapi"
        payload = {
            "client_id": "client-id.apps.googleusercontent.com",
            "refresh_token": "refresh-token-secret",
            "scopes": ["scope-a", "scope-b"],
        }
        save_credential(payload, path)
        assert credential_exists(path)
        assert path.read_bytes() != b"refresh-token-secret"
        assert load_credential(path) == payload


def test_missing_store_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            load_credential(Path(tmp) / "missing.dpapi")


def test_empty_refresh_token_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError):
            save_credential({"client_id": "x", "refresh_token": "", "scopes": ["s"]}, Path(tmp) / "x.dpapi")
