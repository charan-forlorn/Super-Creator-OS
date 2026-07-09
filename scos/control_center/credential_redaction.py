"""Stage 8.3 pure credential redaction helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any

try:
    from .credential_policy_models import (
        CredentialPolicy,
        RedactionFinding,
        RedactionResult,
        create_default_credential_policy,
    )
except ImportError:  # direct-module execution
    from credential_policy_models import (
        CredentialPolicy,
        RedactionFinding,
        RedactionResult,
        create_default_credential_policy,
    )

_FAKE_SENTINEL = "FAKE_" + "SECRET" + "_DO_NOT_USE"
_BEARER_RE = re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{8,}\b")
_SK_RE = re.compile(r"\b" + "sk" + r"-[A-Za-z0-9]{8,}\b")
_ASSIGNMENT_RE = re.compile(
    r"\b(?:" + "|".join(("api" + "_key", "token", "secret", "password")) + r")\b\s*[:=]\s*[^,\s}]+",
    re.IGNORECASE,
)


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _category_for_marker(marker: str) -> str:
    normalized = _normalize_key(marker)
    if "api_key" in normalized:
        return "API_KEY"
    if "token" in normalized or "bearer" in normalized:
        return "TOKEN"
    if "password" in normalized:
        return "PASSWORD"
    if "cookie" in normalized:
        return "COOKIE"
    if "authorization" in normalized:
        return "AUTHORIZATION_HEADER"
    if "credential" in normalized:
        return "GENERIC_SECRET"
    if "secret" in normalized:
        return "GENERIC_SECRET"
    return "UNKNOWN"


def classify_secret_field_name(field_name: object, *, policy: CredentialPolicy | None = None) -> str | None:
    active_policy = policy or create_default_credential_policy()
    normalized = _normalize_key(field_name)
    for marker in active_policy.secret_field_markers:
        if _normalize_key(marker) in normalized:
            return _category_for_marker(marker)
    return None


def classify_secret_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    upper = text.upper()
    if _FAKE_SENTINEL in upper:
        return "GENERIC_SECRET"
    if _BEARER_RE.search(text):
        return "TOKEN"
    if _SK_RE.search(text):
        return "API_KEY"
    if _ASSIGNMENT_RE.search(text):
        return "GENERIC_SECRET"
    if "-----" + "BEGIN" in upper and "PRIVATE" + " KEY" in upper:
        return "PRIVATE_KEY"
    return None


def _finding(path: str, category: str, reason: str, *, redacted: bool) -> RedactionFinding:
    return RedactionFinding(
        finding_id=_stable_id("crf-", path, category, reason, redacted),
        path=path,
        category=category,
        reason=reason,
        redacted=redacted,
    )


def _redact_value(value: Any, *, path: str, policy: CredentialPolicy, findings: list[RedactionFinding]) -> Any:
    category = classify_secret_value(value)
    if category is not None:
        findings.append(_finding(path, category, "secret-like value", redacted=True))
        return policy.redaction_marker
    return value


def _redact_payload(payload: Any, *, path: str, policy: CredentialPolicy, findings: list[RedactionFinding]) -> Any:
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key in sorted(payload, key=lambda item: str(item)):
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            category = classify_secret_field_name(key_text, policy=policy)
            if category is not None:
                findings.append(_finding(child_path, category, "secret-like field name", redacted=True))
                redacted[key_text] = policy.redaction_marker
            else:
                redacted[key_text] = _redact_payload(payload[key], path=child_path, policy=policy, findings=findings)
        return redacted
    if isinstance(payload, (list, tuple)):
        return [
            _redact_payload(item, path=f"{path}[{index}]", policy=policy, findings=findings)
            for index, item in enumerate(payload)
        ]
    return _redact_value(payload, path=path or "$", policy=policy, findings=findings)


def redact_credential_payload(payload, *, policy: CredentialPolicy | None = None) -> RedactionResult:
    active_policy = policy or create_default_credential_policy()
    findings: list[RedactionFinding] = []
    redacted_payload = _redact_payload(payload, path="$", policy=active_policy, findings=findings)
    return RedactionResult(
        accepted=True,
        redacted_payload=redacted_payload,
        findings=tuple(findings),
        warnings=(),
        blockers=(),
    )


__all__ = sorted(
    (
        "classify_secret_field_name",
        "classify_secret_value",
        "redact_credential_payload",
    )
)
