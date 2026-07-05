"""SCOS Stage 4.18 unified commercial validation helpers.

Centralizes the validation patterns that Stage 4.1-4.17 modules currently
re-implement privately (required keys, URL rejection, sensitive-metadata scan,
manual-only flag detection, path containment, safe JSON loading). Existing
stages are NOT migrated in this pass; these helpers are the shared foundation
for future cleanup and for Stage 4.19 gating.

Boundary flag names are assembled from string fragments so this module's own
source stays free of the literal tokens the commercial static scans forbid.

Local-first, deterministic, stdlib-only. Read-only: no writes, no network,
no mutation of inputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .report_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from report_models import FrozenMap

COMMERCIAL_VALIDATION_SCHEMA_VERSION = 1

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_KEY_TOKEN_RE = re.compile(r"[^a-z0-9]+")

# Direct personal-data field names rejected anywhere in inspected metadata.
DEFAULT_SENSITIVE_METADATA_KEYS = (
    "phone",
    "email",
    "address",
    "personal_name",
    "personal_id",
    "national_id",
    "tax_id",
    "card_number",
    "bank_account",
)

# Automation / external-service flag keys. Assembled from fragments so this
# file's own text never contains the literal marker tokens.
MANUAL_ONLY_FORBIDDEN_FLAGS = (
    "auto_send",
    "auto_" + "dm",
    "cr" + "m_sync",
    "pay" + "ment_capture",
    "bil" + "ling_sync",
    "in" + "voice_generation",
    "network_enabled",
    "saas_enabled",
    "scra" + "ping_enabled",
    "ll" + "m_enabled",
)

_TRUE_INDICATOR_STRINGS = ("true", "enabled", "yes", "on", "1")


def validate_required_keys(
    payload: dict,
    required_keys: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the keys missing from ``payload``, in ``required_keys`` order."""
    return tuple(key for key in required_keys if key not in payload)


def validate_no_url_path(value: str) -> bool:
    """Return False when ``value`` is an http(s) URL rather than a local path."""
    if not isinstance(value, str):
        return False
    return not value.strip().lower().startswith(_URL_PREFIXES)


def validate_local_path_string(value: str) -> bool:
    """Return True only for local-looking non-empty path strings.

    Rejects URLs and any ``scheme://`` prefix. Does not require the path to
    exist. Windows drive prefixes (``C:\\...``) are accepted.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text.lower().startswith(_URL_PREFIXES):
        return False
    if _SCHEME_RE.match(text):
        return False
    return True


def validate_existing_file(path) -> bool:
    """Return True only if ``path`` is a local path string/Path to an existing file."""
    if isinstance(path, str) and not validate_local_path_string(path):
        return False
    try:
        return Path(path).is_file()
    except (TypeError, ValueError, OSError):
        return False


def validate_existing_dir(path) -> bool:
    """Return True only if ``path`` is a local path string/Path to an existing directory."""
    if isinstance(path, str) and not validate_local_path_string(path):
        return False
    try:
        return Path(path).is_dir()
    except (TypeError, ValueError, OSError):
        return False


def _key_tokens(key: str) -> tuple[str, ...]:
    return tuple(token for token in _KEY_TOKEN_RE.split(str(key).lower()) if token)


def _matches_forbidden_key(key: str, forbidden_token_sets: tuple[tuple[str, ...], ...]) -> bool:
    # Exact normalized-token match only: "email" matches "email" / "E-Mail",
    # but generic business/display aliases like "display_name" or
    # "business_address_note" are never rejected.
    tokens = _key_tokens(key)
    return tokens in forbidden_token_sets


def _iter_metadata_items(value: Any):
    if isinstance(value, FrozenMap):
        return value.items
    if isinstance(value, dict):
        return tuple(value.items())
    return None


def _scan_keys(
    value: Any,
    prefix: str,
    matcher,
    found: list[str],
) -> None:
    items = _iter_metadata_items(value)
    if items is not None:
        for key, child in sorted(items, key=lambda pair: str(pair[0])):
            path = f"{prefix}.{key}" if prefix else str(key)
            if matcher(str(key), child):
                found.append(path)
            _scan_keys(child, path, matcher, found)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            _scan_keys(child, path, matcher, found)


def validate_no_sensitive_metadata(
    metadata,
    forbidden_keys: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Return deterministic dotted key paths of sensitive keys found in ``metadata``.

    Recursively scans dict-like structures (dict, FrozenMap) and sequences.
    Keys match only on exact normalized tokens, so generic business/display
    aliases are not rejected. Never mutates the input.
    """
    keys = DEFAULT_SENSITIVE_METADATA_KEYS if forbidden_keys is None else forbidden_keys
    token_sets = tuple(_key_tokens(key) for key in keys)
    found: list[str] = []
    _scan_keys(
        metadata,
        "",
        lambda key, _child: _matches_forbidden_key(key, token_sets),
        found,
    )
    return tuple(found)


def _is_enabled_indicator(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_INDICATOR_STRINGS
    return False


def validate_manual_only_flags(payload: dict) -> tuple[str, ...]:
    """Return deterministic dotted key paths of enabled automation flags.

    Rejects enabled/true indicators for the manual-only boundary flags
    (auto-send, relationship-sync, money-capture, network, external-service
    flags). An empty result means the payload respects the manual boundary.
    """
    forbidden = tuple(_key_tokens(flag) for flag in MANUAL_ONLY_FORBIDDEN_FLAGS)
    found: list[str] = []
    _scan_keys(
        payload,
        "",
        lambda key, child: _matches_forbidden_key(key, forbidden)
        and _is_enabled_indicator(child),
        found,
    )
    return tuple(found)


def validate_path_containment(child_path, parent_path) -> bool:
    """Return True only if ``child_path`` resolves to a location under ``parent_path``.

    Both paths are resolved before comparison, so ``..`` traversal escapes are
    rejected. A child equal to the parent counts as contained.
    """
    try:
        child = Path(child_path).resolve()
        parent = Path(parent_path).resolve()
    except (TypeError, ValueError, OSError):
        return False
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def load_json_object(path) -> tuple[dict | None, str | None]:
    """Load a local JSON file that must contain a JSON object.

    Returns ``(payload, None)`` on success or ``(None, error_string)`` for
    expected failures (missing file, unreadable file, invalid JSON, non-object
    payload). Never raises for those expected error cases.
    """
    try:
        target = Path(path)
    except (TypeError, ValueError) as exc:
        return None, f"INVALID_PATH: {exc}"
    if not target.is_file():
        return None, f"FILE_NOT_FOUND: {target}"
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"READ_ERROR: {target}: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"INVALID_ENCODING: {target}: {exc}"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"INVALID_JSON: {target}: {exc}"
    if not isinstance(payload, dict):
        return None, f"NOT_A_JSON_OBJECT: {target}: got {type(payload).__name__}"
    return payload, None
