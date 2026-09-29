from __future__ import annotations

import json
import tempfile
from pathlib import Path

from integrations.learning.youtube_oauth_runtime import refresh_access_token
from integrations.learning.youtube_oauth_store import save_credential


def test_refresh_access_token_uses_encrypted_store_without_exposing_secret(tmp_path: Path) -> None:
    store = tmp_path / "yt.dpapi"
    save_credential({
        "client_id": "123.apps.googleusercontent.com",
        "refresh_token": "refresh-secret",
        "scopes": ["scope"],
    }, store)

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"access_token": "access-secret", "expires_in": 3600}).encode()

    seen = {}
    def opener(request, timeout=0):
        seen["body"] = request.data.decode()
        seen["timeout"] = timeout
        return Response()

    token = refresh_access_token(store, opener=opener, timeout=7.0)
    assert token == "access-secret"
    assert "refresh-secret" in seen["body"]
    assert "client_id=123.apps.googleusercontent.com" in seen["body"]
    assert seen["timeout"] == 7.0
