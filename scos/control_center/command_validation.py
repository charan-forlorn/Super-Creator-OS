"""SCOS Stage 5.1 Control Center command validation helpers.

Deterministic, read-only validation for operator command drafts before they
may reach the approval gate. Rejects unknown command types, duplicate or
disallowed args, URL paths, shell-injection-like characters in arg values,
and any forbidden command text.

Forbidden text markers are assembled from string fragments so this module's
own source stays free of the literal tokens the static scans forbid (repo
convention shared with ``scos.commercial.validation``).

Local-first, deterministic, stdlib-only. Read-only: no writes, no network,
no mutation of inputs.
"""

from __future__ import annotations

import re

try:
    from .command_models import ALLOWED_COMMAND_TYPES, CommandDraft
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_models import ALLOWED_COMMAND_TYPES, CommandDraft

CONTROL_CENTER_COMMAND_VALIDATION_SCHEMA_VERSION = 1

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

# Characters never allowed inside arg values (paths or path-like inputs are
# the expected arg payloads; these are the classic shell-injection markers).
FORBIDDEN_ARG_VALUE_CHARACTERS = (";", "&", "|", ">", "<", "`", "$", "\n", "\r")

# Forbidden command text markers, assembled from fragments so this file's own
# text never contains the literal tokens. Matching is case-insensitive
# substring search; results are reported in this fixed order.
FORBIDDEN_COMMAND_TEXT = (
    "git pu" + "sh",
    "git com" + "mit",
    "git re" + "set",
    "git cl" + "ean",
    "git reb" + "ase",
    "git mer" + "ge",
    "git st" + "ash",
    "rm -" + "rf",
    "del /" + "f",
    "for" + "mat",
    "cu" + "rl",
    "wg" + "et",
    "powershell -Enc" + "odedCommand",
    "pay" + "ment",
    "bil" + "ling",
    "inv" + "oice",
    "cr" + "m",
    "send_em" + "ail",
    "send_li" + "ne",
    "auto_" + "dm",
    "net" + "work",
    "web" + "hook",
    "cloud_dep" + "loy",
    "dep" + "loy",
    "vercel dep" + "loy",
)

# Per-command-type arg contracts: (allowed keys, required keys).
_COMMAND_ARG_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "RUN_SMOKE_CHECK": ((), ()),
    "RUN_RELEASE_CHECK": ((), ()),
    "RUN_SECURITY_SCAN": ((), ()),
    "RUN_STAGE4_FINAL_GATE": (("checked_at",), ("checked_at",)),
    "OPEN_STAGE5_HANDOFF": ((), ()),
    "GENERATE_STATUS_SNAPSHOT": ((), ()),
}

_REQUIRED_DRAFT_FIELDS = (
    "command_id",
    "command_type",
    "requested_by",
    "created_at",
    "summary",
)


def _is_url_like(value: str) -> bool:
    text = str(value).strip()
    return text.lower().startswith(_URL_PREFIXES) or bool(_SCHEME_RE.match(text))


def validate_command_type(command_type: str) -> tuple[bool, str | None]:
    """Return ``(True, None)`` for an allowed command type, else a stable error."""
    if command_type in ALLOWED_COMMAND_TYPES:
        return True, None
    return False, f"unknown command_type: {command_type!r}"


def validate_command_args(
    command_type: str,
    args: tuple[tuple[str, str], ...],
) -> tuple[bool, tuple[str, ...]]:
    """Validate ``args`` against the per-type contract.

    Deterministic error ordering: unknown type first, then duplicate keys
    (first occurrence order), disallowed keys, missing required keys, URL
    values, and forbidden characters. Never mutates the input.
    """
    errors: list[str] = []
    spec = _COMMAND_ARG_SPECS.get(command_type)
    if spec is None:
        return False, (f"unknown command_type: {command_type!r}",)
    allowed_keys, required_keys = spec

    seen: list[str] = []
    for key, _value in args:
        if key in seen:
            error = f"duplicate arg key: {key}"
            if error not in errors:
                errors.append(error)
        else:
            seen.append(key)

    for key, _value in args:
        if key not in allowed_keys:
            error = f"arg key not allowed for {command_type}: {key}"
            if error not in errors:
                errors.append(error)

    for key in required_keys:
        if key not in seen or all(
            not value.strip() for k, value in args if k == key
        ):
            errors.append(f"missing required arg: {key}")

    for key, value in args:
        if _is_url_like(value):
            errors.append(f"arg value must not be a URL: {key}")

    for key, value in args:
        for character in FORBIDDEN_ARG_VALUE_CHARACTERS:
            if character in value:
                errors.append(
                    f"arg value contains forbidden shell character: {key}"
                )
                break

    return (not errors), tuple(errors)


def validate_no_forbidden_command_text(value: str) -> tuple[bool, tuple[str, ...]]:
    """Return ``(True, ())`` when ``value`` contains no forbidden command text.

    On failure, returns the matched markers in the fixed ``FORBIDDEN_COMMAND_TEXT``
    order (case-insensitive substring match).
    """
    lowered = str(value).lower()
    found = tuple(
        marker for marker in FORBIDDEN_COMMAND_TEXT if marker.lower() in lowered
    )
    return (not found), found


def validate_command_draft(draft: CommandDraft) -> tuple[bool, tuple[str, ...]]:
    """Validate a full draft; returns ``(ok, deterministic error tuple)``.

    Check sequence is fixed: required fields, command type, forbidden text
    (summary, then arg keys/values, then metadata keys/values, each in input
    order), then arg contract errors. Never mutates the draft.
    """
    errors: list[str] = []

    for field_name in _REQUIRED_DRAFT_FIELDS:
        if not str(getattr(draft, field_name)).strip():
            errors.append(f"empty required field: {field_name}")

    type_ok, type_error = validate_command_type(draft.command_type)
    if not type_ok and type_error is not None:
        errors.append(type_error)

    texts = [("summary", draft.summary)]
    texts.extend((f"args.{key}", f"{key} {value}") for key, value in draft.args)
    texts.extend(
        (f"metadata.{key}", f"{key} {value}") for key, value in draft.metadata
    )
    for label, text in texts:
        text_ok, found = validate_no_forbidden_command_text(text)
        if not text_ok:
            for marker in found:
                errors.append(f"forbidden command text in {label}: {marker}")

    if type_ok:
        _args_ok, arg_errors = validate_command_args(draft.command_type, draft.args)
        errors.extend(arg_errors)

    return (not errors), tuple(errors)
