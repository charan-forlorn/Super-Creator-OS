from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.scos_youtube_oauth import extract_client_id, _pkce


def test_extract_client_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "client.txt"
        p.write_text("key\n123456789012-abcdefghijklmnop.apps.googleusercontent.com\n", encoding="utf-8")
        assert extract_client_id(p) == "123456789012-abcdefghijklmnop.apps.googleusercontent.com"


def test_extract_client_id_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "client.txt"
        p.write_text("no client id", encoding="utf-8")
        try:
            extract_client_id(p)
        except ValueError as exc:
            assert "client ID" in str(exc)
        else:
            raise AssertionError("missing client ID must fail closed")


def test_pkce_challenge_is_not_verifier() -> None:
    verifier, challenge = _pkce()
    assert 43 <= len(verifier) <= 128
    assert verifier != challenge
    assert "=" not in challenge



def test_load_installed_client_json() -> None:
    from scripts.scos_youtube_oauth import load_client_config
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "client.json"
        p.write_text('{"installed":{"client_id":"123.apps.googleusercontent.com","client_secret":"x","redirect_uris":["http://localhost"]}}', encoding="utf-8")
        cfg = load_client_config(p)
        assert cfg["type"] == "installed"
        assert cfg["client_id"] == "123.apps.googleusercontent.com"
        assert cfg["client_secret"] == "x"


def test_bare_client_id_cannot_bypass_redirect_preflight() -> None:
    from scripts.scos_youtube_oauth import authorize, load_client_config
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "client.txt"
        p.write_text("123456789012-abcdefghijklmnop.apps.googleusercontent.com", encoding="utf-8")
        cfg = load_client_config(p)
        try:
            authorize(cfg, open_browser=False)
        except RuntimeError as exc:
            assert "OAUTH_CLIENT_TYPE_UNKNOWN" in str(exc)
        else:
            raise AssertionError("bare client id must not start an ambiguous OAuth redirect flow")
