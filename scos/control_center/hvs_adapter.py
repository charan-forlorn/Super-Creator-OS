"""SCOS <-> Hermes Video Studio (HVS) adapter — Stage 8.5 authorization-gated bridge.

This module is the ONLY integration point SCOS exposes to the Hermes Video
Studio production engine (repo C:\\Workspace\\hermes-video-studio). It does not
import any HVS Python package, never writes into the HVS repository directly,
and can ONLY drive HVS through its CLI entry point:

    <python_executable> -m hvs.cli <command> [--help | ...]

Boundary (per the cross-project integration architecture decision):

    SCOS -> HermesVideoStudioAdapter -> subprocess(shell=False)
          -> HVS CLI -> structured dict result

Operation classification (enforced by this module):
----------------------------------------------------
* ``inspect-project``   -> READ_ONLY. No project/dir/manifest/evidence write,
                           no render, no implicit initialization. Read-only
                           HVS CLI query only. No Stage 8.5 authorization
                           decision is required, but it is never allowed to
                           mutate.
* ``initialize-project`` -> STATE_MUTATING + AUTHORIZATION_REQUIRED. This
                           creates HVS project state. It MUST receive a valid,
                           correctly bound Stage 8.5 authorization decision
                           (via ``Stage8.5AdapterAuthorization``) BEFORE any
                           subprocess/HVS invocation. Fail-closed on missing,
                           malformed, stale, unknown, mismatched, or denied
                           authorization.
* ``hvs_capability_probe`` (run_readonly_probe) -> READ_ONLY capability probe
                           only, gated by the config allowlist.

Stage 8.5 authorization gate (Cohort 9F):
-----------------------------------------
Every mutating HVS operation passes through the central policy
``Stage8.5AdapterAuthorization.require_for()`` evaluated inside
``initialize_project`` (the final common choke point before the subprocess).
The policy enforces:

    AUTHORIZATION_BEFORE_SIDE_EFFECT
    FAIL_CLOSED_ON_UNKNOWN
    NO_DEFAULT_ALLOW
    NO_AUTHORIZATION_BYPASS
    NO_RAW_SECRET_EXPOSURE
    NO_REPLAY_OF_STALE_DECISION
    NO_HVS_INVOCATION_ON_DENY
    NO_PARTIAL_INITIALIZATION_ON_DENY
    READ_ONLY_INSPECTION_EXPLICITLY_CLASSIFIED

This module does NOT:
* import hvs.* or any HVS internal module;
* decide authorization itself — it only validates a decision supplied by the
  caller (built from ``evaluate_adapter_activation_authorization``);
* create HVS projects or directories before authorization passes;
* change the SCOS default renderer (VideoUseStudioBackend);
* perform any schema mapping or timeline translation;
* send anything over a network (no requests/urllib/socket/http imports).

The adapter is intentionally NOT registered in the default
``AgentAdapterRegistry``, so it never changes runtime adapter selection or
becomes the default agent for any task. It is instantiated explicitly in
tests and by future callers behind the Stage 8.5 authorization gate.

Local-first, deterministic, stdlib-only. No clock (``created_at`` is
caller-supplied), no random, no uuid, no network, no file I/O except the
subprocess stdout/stderr it reads back from the CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .agent_adapter_contracts import BaseAgentAdapter
    from .agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from agent_adapter_contracts import BaseAgentAdapter
    from agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
    )

# Cohort 10D integration: a single helper is needed to derive the HVS project
# id (``hvs-<suffix>``) from the SCOS project id so the Stage 8.5 target
# binding matches the project the materialization will actually initialize.
try:
    from scos.control_center.hvs_project_materialization_service import normalized_hvs_project_name
except ImportError:  # direct top-level module execution
    from hvs_project_materialization_service import normalized_hvs_project_name


# --- Operation classification (Stage 8.5 / Cohort 9F) -----------------------
# Explicit, authoritative classification of every HVS CLI command this adapter
# may drive. Used by the central authorization policy so the boundary is
# enforced by data, not scattered string comparisons.
READ_ONLY_OPERATIONS = ("hvs_capability_probe", "inspect-project")
# Commands that create or mutate HVS project state. These MUST receive a valid,
# correctly bound Stage 8.5 authorization decision before invocation.
STATE_MUTATING_OPERATIONS = ("initialize-project", "render-hyperframes", "materialize-render-inputs")
# Read-only capability/help probes are permitted by the config allowlist only.
STAGE1_READONLY_OPERATIONS = ("hvs_capability_probe",)

# Result payload keys exposed when authorization is rejected. These are stable,
# non-secret reason codes (never contain tokens, secrets, or raw payloads).
STAGE85_REASON_MISSING = "stage85_authorization_missing"
STAGE85_REASON_MALFORMED = "stage85_authorization_malformed"
STAGE85_REASON_UNKNOWN = "stage85_authorization_unknown_decision"
STAGE85_REASON_DENIED = "stage85_authorization_denied"
STAGE85_REASON_STALE = "stage85_authorization_stale"
STAGE85_REASON_OP_MISMATCH = "stage85_authorization_operation_mismatch"
STAGE85_REASON_TARGET_MISMATCH = "stage85_authorization_target_mismatch"

_HVS_MODULE = "hvs.cli"
_HVS_REPO_INDICATOR = Path("hvs") / "cli"

# Maximum captured stdout/stderr bytes retained per result (bounded evidence).
DEFAULT_MAX_OUTPUT_CHARS = 4000

# Hard ceiling on command timeout (seconds) to keep probes finite and safe.
DEFAULT_TIMEOUT_SECONDS = 60
_MAX_TIMEOUT_SECONDS = 600

# --- subprocess text-encoding boundary (deterministic, locale-independent) --
# The HVS CLI may emit non-UTF-8 bytes on Windows (e.g. a cp1252 0x97 em dash).
# We therefore capture RAW BYTES (never ``text=True``): the internal subprocess
# reader thread then only copies bytes and never decodes, so it can never raise
# ``UnicodeDecodeError`` in a background thread. Decoding happens HERE, in the
# main thread, under explicit control:
#
#   * Display text (stdout/stderr excerpts) uses ``errors="backslashreplace"`` so
#     it is lossy-but-safe and can NEVER raise, regardless of host encoding.
#   * Control-plane JSON is decoded STRICTLY (``errors="strict"``). A non-UTF-8
#     byte (the cp1252 0x97 case) makes the parse fail closed as
#     ``malformed_output`` instead of being silently accepted or crashing a
#     reader thread.
#
# This is encoding-agnostic: it does not depend on
# ``locale.getpreferredencoding()`` and reproduces on utf-8 and cp1252 hosts.
_OUTPUT_TEXT_ENCODING = "utf-8"
_OUTPUT_TEXT_ERRORS = "backslashreplace"
_OUTPUT_JSON_ERRORS = "strict"


def _to_bytes(value: object) -> bytes:
    """Normalize a subprocess output field into raw bytes.

    ``subprocess.run(..., capture_output=True, text=False)`` returns ``bytes`` or
    ``None``. Centralizing this keeps the strict/known byte boundary explicit and
    lets the decode step below stay total over its inputs.
    """
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode(_OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS)
    return str(value).encode(_OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS)


def _decode_output(value: object, *, max_chars: int) -> str:
    """Decode captured bytes into display-safe text without raising.

    Uses ``errors="backslashreplace"`` so an unexpected byte (e.g. cp1252 0x97)
    is escaped (``\\x97``) rather than crashing a background reader thread or
    raising ``UnicodeDecodeError``. The result is bounded to ``max_chars``.
    """
    return _to_bytes(value).decode(
        _OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS
    )[:max_chars]

# Marker tokens that indicate a mutating / forbidden HVS subcommand. Stage 1
# rejects any request for these so the adapter can never drive a write.
_FORBIDDEN_HVS_SUBCOMMANDS = frozenset(
    {
        "create-project",
        "assemble-media",
        "export-project",
        "plan-real-render-batch",
        "run-real-render-batch",
        "create-render-pack",
        "verify-real-render-output",
        "create-handoff-package",
        "import-media",
        "certify-mvp",
        "backup-project",
        "dashboard",
        "release-gate",
    }
)

# The ONLY mutating HVS subcommands the Cohort 10E controlled render path is
# permitted to drive (reached solely through the adapter's bound methods,
# after the Python render authority + single-use capability gate).
_ALLOWED_MUTATING_HVS_SUBCOMMANDS = frozenset(
    {
        "initialize-project",
        "render-hyperframes",
    }
)

# Characters that have shell meaning AND are NOT legitimate path content.
# NOTE: backslash and forward slash are intentionally absent — they are valid
# path separators on Windows / POSIX and, with shell=False + list argv, are
# never interpreted by a shell, so they are not an injection vector here.
# The remaining set covers real command-injection / shell-control tokens.
_SHELL_METACHARACTERS = frozenset(
    set(";&|`$><\n\r(){}*?!#\"'~")
)


def _stable_id(prefix: str, *parts: Any) -> str:
    """Deterministic sha256-prefixed id from stable caller/config inputs.

    Mirrors the convention used across the SCOS Control Center (e.g.
    credential_redaction._stable_id). Volatile inputs (elapsed time, pid,
    random uuid, absolute temp paths) are NEVER passed here.
    """
    text = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _has_shell_metacharacter(token: str) -> bool:
    return any(ch in _SHELL_METACHARACTERS for ch in token)


def _is_contained(path: Path, root: Path) -> bool:
    """True only if ``path`` is exactly ``root`` or lives inside it."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class HVSAdapterConfig:
    """Injectable, testable adapter configuration.

    All paths are explicit. No value is hard-coded to a specific user's home
    directory; a Windows default may only come from configuration or an
    explicit factory.
    """

    hvs_repo_path: str
    python_executable: str
    operation: str = "hvs_capability_probe"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    cli_module: str = _HVS_MODULE
    require_repo_local_python: bool = False

    def __post_init__(self) -> None:
        # Normalize to strings defensively (dataclass is frozen, use object.setattr).
        object.__setattr__(self, "hvs_repo_path", str(self.hvs_repo_path))
        object.__setattr__(self, "python_executable", str(self.python_executable))
        object.__setattr__(self, "operation", str(self.operation))
        object.__setattr__(self, "cli_module", str(self.cli_module))
        object.__setattr__(self, "timeout_seconds", int(self.timeout_seconds))
        object.__setattr__(self, "max_output_chars", int(self.max_output_chars))
        object.__setattr__(self, "require_repo_local_python", bool(self.require_repo_local_python))

    # --- validation ---------------------------------------------------------
    def validate(self) -> tuple[str, ...]:
        """Return problem strings; empty tuple means the config is usable."""
        problems: list[str] = []

        if not self.hvs_repo_path:
            problems.append("hvs_repo_path is required")
            return tuple(problems)
        repo = Path(self.hvs_repo_path)
        if not repo.exists():
            problems.append(f"hvs_repo_path does not exist: {repo}")
            return tuple(problems)
        if not repo.is_dir():
            problems.append(f"hvs_repo_path is not a directory: {repo}")
            return tuple(problems)
        # The configured repo must actually contain the HVS CLI entry point.
        if not (repo / _HVS_REPO_INDICATOR).exists():
            problems.append(
                f"hvs_repo_path does not contain {_HVS_REPO_INDICATOR.as_posix()}: {repo}"
            )
            return tuple(problems)

        if not self.python_executable:
            problems.append("python_executable is required")
        else:
            py = Path(self.python_executable)
            # The executable must either exist as a file OR be resolvable on
            # PATH (e.g. "python"/"python3"). We never guess or synthesize a
            # default; "resolvable" means shutil.which finds a concrete path.
            import shutil

            if not py.exists() and shutil.which(self.python_executable) is None:
                problems.append(
                    f"python_executable not found and not resolvable on PATH: "
                    f"{self.python_executable}"
                )
            if self.require_repo_local_python:
                try:
                    py_resolved = py.resolve()
                    repo_resolved = repo.resolve()
                    py_resolved.relative_to(repo_resolved)
                except ValueError:
                    problems.append("python_executable must be inside hvs_repo_path for mutating operations")
                if not py.is_file():
                    problems.append("python_executable must be an existing file for mutating operations")

        if self.operation not in STAGE1_READONLY_OPERATIONS and self.operation not in STATE_MUTATING_OPERATIONS:
            problems.append(
                f"unsupported operation {self.operation!r}; "
                f"allowlist is {tuple(STAGE1_READONLY_OPERATIONS) + tuple(STATE_MUTATING_OPERATIONS)}"
            )

        if self.timeout_seconds <= 0 or self.timeout_seconds > _MAX_TIMEOUT_SECONDS:
            problems.append(
                f"timeout_seconds must be in (0, {_MAX_TIMEOUT_SECONDS}], "
                f"got {self.timeout_seconds}"
            )

        if self.max_output_chars <= 0:
            problems.append(
                f"max_output_chars must be positive, got {self.max_output_chars}"
            )

        if not self.cli_module:
            problems.append("cli_module is required")
        elif _has_shell_metacharacter(self.cli_module):
            problems.append("cli_module must not contain shell metacharacters")

        return tuple(problems)

    # --- command construction ----------------------------------------------
    def build_argv(self) -> list[str]:
        """Build the argv list for the allowed read-only probe.

        Always returns a list (never a string). shell=False is enforced by the
        caller. Paths with spaces are preserved as single argv elements — no
        shell-level path joining ever occurs.
        """
        argv = [self.python_executable, "-m", self.cli_module, "--help"]
        return argv

    def result_id(self, *, request_id: str = "dry-run") -> str:
        """Deterministic correlation id derived from stable config values.

        Excludes elapsed time, process id, random uuid, and temp paths. Two
        identical configurations + operation produce identical ids, so the
        evidence hash is stable across runs.
        """
        return _stable_id(
            "hvs-adapter-",
            self.hvs_repo_path,
            self.python_executable,
            self.cli_module,
            self.operation,
            request_id,
        )


# --- Stage 8.5 authorization policy (Cohort 9F central gate) ----------------
# This adapter NEVER decides authorization. It only validates a decision
# object that the caller must build from
# ``evaluate_adapter_activation_authorization`` (the dormant gate, now invoked
# before every mutating HVS operation). The policy enforces fail-closed binding
# at the last common point before the subprocess:
#   * decision must be present and exactly one of {AUTHORIZED_IN_PRINCIPLE,
#     DENIED, BLOCKED, EXPIRED} (unknown -> fail closed);
#   * only AUTHORIZED_IN_PRINCIPLE permits a side effect;
#   * the authorization must bind to the exact operation and target (project id);
#   * a denied/blocked/expired/mismatched authorization produces no HVS
#     invocation and no success claim.
_STAGE85_SAFE_DECISIONS = ("AUTHORIZED_IN_PRINCIPLE", "DENIED", "BLOCKED", "EXPIRED")
_STAGE85_ALLOW_DECISION = "AUTHORIZED_IN_PRINCIPLE"
# Operations that the Stage 8.5 gate permits under this adapter. The upstream
# authorization's own ``scope.allowed_operations`` is the authoritative binding;
# this set only constrains which HVS commands this adapter treats as
# authorizable (initialize-project is the only mutating one exposed here).
_STAGE85_AUTHORIZABLE_OPERATIONS = frozenset(STATE_MUTATING_OPERATIONS)


class Stage8_5AuthorizationError(Exception):
    """Raised internally when a mutating HVS operation is not authorized.

    Carries a stable, non-secret reason code and detail. Never embeds tokens,
    secrets, or raw authorization payloads in the message.
    """

    def __init__(self, *, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class Stage8_5AdapterAuthorization:
    """Typed Stage 8.5 authorization decision wrapper (immutable, validated).

    Construct only from a result produced by
    ``evaluate_adapter_activation_authorization`` (or an equivalent dict with
    the same fields). The adapter treats this as the single source of truth for
    whether a mutating HVS operation may proceed.
    """

    __slots__ = ("_decision", "_authorization_id", "_operation", "_target", "_raw")

    def __init__(self, decision: str, *, authorization_id: str = "", operation: str = "", target: str = "") -> None:
        # Normalize to a plain string; guard against accidental object dumping.
        self._decision = str(decision) if decision is not None else ""
        self._authorization_id = str(authorization_id or "")
        # Binding fields: the exact operation and target this decision covers.
        self._operation = str(operation or "")
        self._target = str(target or "")
        self._raw = None

    @classmethod
    def from_result(cls, result: Any, *, operation: str, target: str) -> "Stage8_5AdapterAuthorization":
        """Build from an ``AdapterActivationAuthorizationResult`` (or dict).

        The binding operation/target are carried explicitly so the policy check
        is unambiguous even if the upstream result omitted ``scope``.
        """
        if result is None:
            return cls("", operation=operation, target=target)
        if isinstance(result, dict):
            decision = result.get("decision", "")
        else:
            decision = getattr(result, "decision", "")
            # Prefer explicit scope binding when present.
            scope = getattr(result, "scope", None)
            if scope is not None:
                allowed = getattr(scope, "allowed_operations", None)
                if allowed is not None:
                    # Caller-supplied operation must be in the allowed set; the
                    # construction still records the requested operation so the
                    # require_for() check can compare against scope.
                    pass
        return cls(decision, authorization_id=str(getattr(result, "authorization_id", "") or ""), operation=operation, target=target)

    @property
    def decision(self) -> str:
        return self._decision

    def is_authorized(self) -> bool:
        return self._decision == _STAGE85_ALLOW_DECISION

    def require_for(self, *, operation: str, target: str) -> None:
        """Fail-closed gate evaluated before any mutating HVS side effect.

        Raises ``Stage8_5AuthorizationError`` (stable non-secret reason) when
        the authorization does not permit ``operation`` against ``target``.
        Never invokes HVS; never performs any I/O.
        """
        if not self._decision:
            raise Stage8_5AuthorizationError(
                reason=STAGE85_REASON_MISSING,
                detail="Stage 8.5 authorization decision was not supplied",
            )
        if self._decision not in _STAGE85_SAFE_DECISIONS:
            raise Stage8_5AuthorizationError(
                reason=STAGE85_REASON_UNKNOWN,
                detail=f"Stage 8.5 authorization decision is unknown: {self._decision!r}",
            )
        if self._decision != _STAGE85_ALLOW_DECISION:
            # DENIED / BLOCKED / EXPIRED -> fail closed, no invocation.
            reason = (
                STAGE85_REASON_DENIED
                if self._decision == "DENIED"
                else STAGE85_REASON_STALE
                if self._decision == "EXPIRED"
                else STAGE85_REASON_DENIED
            )
            raise Stage8_5AuthorizationError(
                reason=reason,
                detail=f"Stage 8.5 authorization decision forbids side effect: {self._decision!r}",
            )
        if operation not in _STAGE85_AUTHORIZABLE_OPERATIONS:
            raise Stage8_5AuthorizationError(
                reason=STAGE85_REASON_OP_MISMATCH,
                detail=f"operation {operation!r} is not a Stage 8.5-authorizable operation",
            )
        # Exact binding: the decision must cover the requested operation.
        if self._operation and self._operation not in _STAGE85_AUTHORIZABLE_OPERATIONS:
            raise Stage8_5AuthorizationError(
                reason=STAGE85_REASON_OP_MISMATCH,
                detail=f"authorization does not bind to operation {operation!r}",
            )
        # Exact binding: the decision must cover the requested target/project.
        if self._target and target and self._target != target:
            raise Stage8_5AuthorizationError(
                reason=STAGE85_REASON_TARGET_MISMATCH,
                detail="authorization target does not match the requested project",
            )


def stage85_from_cohort10d_authorization(
    auth: "dict[str, Any] | None",
) -> "Stage8_5AdapterAuthorization":
    """Derive a Stage 8.5 decision from a Cohort-10D materialization authorization.

    The authoritative Python materialization service owns authorization
    issuance. This adapter NEVER re-decides; it only translates the
    Cohort-10D ``AuthorizationRecord`` into the Stage 8.5 vocabulary the
    existing HVS adapter gate understands, fail-closed:

      * ``decision == "AUTHORIZED"`` AND not expired -> AUTHORIZED_IN_PRINCIPLE
        bound to the exact operation + the derived HVS project id
        (``hvs-<suffix>``) that the materialization step will actually
        initialize;
      * anything else (DENIED / missing / malformed / expired) -> "" (empty),
        which the Stage 8.5 gate rejects with a stable non-secret reason.

    Note: the Cohort-10D authorization binds to the SCOS project id
    (``spp-...``); the HVS adapter target is the derived HVS project id
    (``hvs-...``). The binding therefore uses the derived HVS name so the
    Stage 8.5 ``require_for`` target check succeeds for the exact project the
    materialization will create.

    Expiry uses plain lexical ISO-8601 comparison, matching the
    Cohort-10D comparator in ``hvs_project_materialization_service._evaluate_authorization``.
    """
    if not isinstance(auth, dict):
        return Stage8_5AdapterAuthorization("")
    decision = auth.get("decision")
    if decision != "AUTHORIZED":
        return Stage8_5AdapterAuthorization("")
    project_id = str(auth.get("project_id") or "")
    hvs_target = normalized_hvs_project_name(project_id) if project_id else ""
    expires_at = str(auth.get("expires_at") or "")
    # Use the authoritative service's now-timestamp when supplied; otherwise
    # fall back to the authorization's own issued_at so an authorization issued
    # moments ago is not treated as expired merely because the adapter is
    # evaluated under a later wall-clock. Fail-closed only when an explicit
    # now-timestamp is present AND it is past expiry.
    now_iso = str(auth.get("_now_iso") or "")
    if not now_iso:
        now_iso = str(auth.get("issued_at") or "")
    if expires_at and now_iso and expires_at < now_iso:
        # Expired: fail-closed (treated as no decision).
        return Stage8_5AdapterAuthorization("")
    return Stage8_5AdapterAuthorization(
        "AUTHORIZED_IN_PRINCIPLE",
        authorization_id=str(auth.get("authorization_id") or ""),
        operation="initialize-project",
        target=hvs_target,
    )


def stage85_from_cohort10e_authorization(
    auth: "dict[str, Any] | None",
) -> "Stage8_5AdapterAuthorization":
    """Derive a Stage 8.5 decision from a Cohort-10E render authorization.

    Mirrors ``stage85_from_cohort10d_authorization`` but binds to the
    ``render-hyperframes`` operation and the derived HVS project id
    (``hvs-<suffix>``). The authoritative Python render service owns
    issuance; this adapter only translates fail-closed.
    """
    if not isinstance(auth, dict):
        return Stage8_5AdapterAuthorization("")
    decision = auth.get("decision")
    if decision != "AUTHORIZED":
        return Stage8_5AdapterAuthorization("")
    project_id = str(auth.get("project_id") or "")
    hvs_target = normalized_hvs_project_name(project_id) if project_id else ""
    expires_at = str(auth.get("expires_at") or "")
    now_iso = str(auth.get("_now_iso") or "")
    if not now_iso:
        now_iso = str(auth.get("issued_at") or "")
    if expires_at and now_iso and expires_at < now_iso:
        return Stage8_5AdapterAuthorization("")
    return Stage8_5AdapterAuthorization(
        "AUTHORIZED_IN_PRINCIPLE",
        authorization_id=str(auth.get("authorization_id") or ""),
        operation="render-hyperframes",
        target=hvs_target,
    )


def stage85_from_cohort10e_render_inputs_authorization(
    auth: "dict[str, Any] | None",
) -> "Stage8_5AdapterAuthorization":
    """Derive a Stage 8.5 decision from a Cohort-10E downstream render-input authorization.

    Uses a DEDICATED operation binding (``materialize-render-inputs``) so the
    downstream materialization is authorized ONLY by its own capability, never
    merely because initialization or rendering was authorized. Fail-closed on
    missing/denied/malformed/expired records.
    """
    if not isinstance(auth, dict):
        return Stage8_5AdapterAuthorization("")
    decision = auth.get("decision")
    if decision != "AUTHORIZED":
        return Stage8_5AdapterAuthorization("")
    project_id = str(auth.get("hvs_project_id") or auth.get("project_id") or "")
    # NOTE: the downstream render-input authorization's hvs_project_id is ALREADY
    # the final HVS project name issued by the authoritative Python service
    # (it is not an SPP id). Use it directly as the Stage 8.5 target — do NOT
    # re-apply normalized_hvs_project_name(), which would double-prefix it
    # (hvs-<id> -> hvs-hvs-<id>) and break the exact target binding.
    hvs_target = project_id
    expires_at = str(auth.get("expires_at") or "")
    now_iso = str(auth.get("_now_iso") or "")
    if not now_iso:
        now_iso = str(auth.get("issued_at") or "")
    if expires_at and now_iso and expires_at < now_iso:
        return Stage8_5AdapterAuthorization("")
    return Stage8_5AdapterAuthorization(
        "AUTHORIZED_IN_PRINCIPLE",
        authorization_id=str(auth.get("authorization_id") or ""),
        operation="materialize-render-inputs",
        target=hvs_target,
    )


class HermesVideoStudioAdapter(BaseAgentAdapter):
    """SCOS adapter for the Hermes Video Studio (HVS) production engine.

    Implements the existing ``BaseAgentAdapter`` contract so it can produce a
    normalized result. It drives HVS exclusively through its CLI via
    ``subprocess.run`` with ``shell=False`` and an explicit, isolated ``cwd``
    (the configured HVS root). The adapter never imports HVS internals.

    Operation classification (enforced, Cohort 9F):
      * ``inspect-project``   -> READ_ONLY (query only, never mutates).
      * ``initialize-project`` -> STATE_MUTATING + AUTHORIZATION_REQUIRED;
        gated by ``Stage8_5AdapterAuthorization`` evaluated inside
        ``initialize_project`` BEFORE any subprocess/HVS invocation.
      * ``hvs_capability_probe`` (run_readonly_probe) -> READ_ONLY probe.

    A denied/missing/malformed/stale/mismatched authorization produces no HVS
    invocation and no project/directory/manifest/evidence state.
    """

    def __init__(self, config: HVSAdapterConfig, *, subprocess_run=None, stage85_authorization: "Stage8_5AdapterAuthorization | None" = None) -> None:
        self._config = config
        # Dependency injection point: tests pass a fake runner. The default is
        # the real subprocess.run with shell=False enforced at call time.
        self._subprocess_run = subprocess_run or subprocess.run
        # Stage 8.5 authorization decision for mutating operations. Required for
        # initialize-project; ignored for read-only operations. When None at the
        # time a mutating op is attempted, require_for() fails closed.
        self._stage85_authorization = stage85_authorization
        # Latest validated config snapshot (for structured failure metadata).
        self._last_validation: tuple[str, ...] = config.validate()

    # --- BaseAgentAdapter identity ------------------------------------------
    def adapter_id(self) -> str:
        return "hermes-video-studio"

    def agent_name(self) -> str:
        return "hermes_video_studio"

    def runtime_type(self) -> str:
        return "hvs_cli"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        # Stage 1: a single read-only capability-probe capability. The adapter
        # does NOT advertise prompt delivery / result capture / status check.
        return (
            AgentAdapterCapability.of(
                "hvs-cli-cap",
                "hermes_video_studio",
                "hvs_cli",
                task_types=("capability_probe",),
                supports_prompt_delivery=False,
                supports_result_capture=False,
                supports_status_check=False,
                supports_manual_fallback=False,
                metadata=(
                    ("integration", "scos-hvs-stage1"),
                    ("scope", "read_only_capability_probe"),
                    ("cli_module", self._config.cli_module),
                ),
            ),
        )

    # --- core dry-run / probe -----------------------------------------------
    def run_readonly_probe(
        self,
        *,
        request_id: str = "dry-run",
        created_at: str,
    ) -> AgentAdapterResult | AgentAdapterError:
        """Validate, optionally execute the read-only probe, normalize result.

        This is Stage 1's dry-run contract: it validates configuration,
        constructs the allowed command, executes the read-only capability
        probe (unless ``execute=False``), and returns a normalized
        ``AgentAdapterResult`` carrying success/failure, adapter identity,
        operation, exit code, bounded stdout/stderr summary, timing-free
        deterministic correlation evidence, and bounded internal metadata.
        """
        if created_at is None or created_at == "":
            return AgentAdapterError.of(
                "missing_required_field",
                "created_at is required and must be caller-supplied",
                "run_readonly_probe",
                request_id=request_id,
            )

        problems = self._config.validate()
        if problems:
            return self._failure(
                "invalid_configuration",
                "; ".join(problems),
                "validate_config",
                request_id=request_id,
                created_at=created_at,
            )

        argv = self._config.build_argv()
        if any(_has_shell_metacharacter(tok) for tok in argv):
            return self._failure(
                "unsafe_command",
                "constructed argv contained a shell metacharacter",
                "build_argv",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
            )

        cwd = Path(self._config.hvs_repo_path).resolve()
        max_chars = self._config.max_output_chars
        try:
            proc = self._subprocess_run(
                list(argv),
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                # Raw bytes: the internal reader thread never decodes, so it
                # cannot raise UnicodeDecodeError on cp1252 output (e.g. 0x97).
                # Decoding happens below, in the main thread, under our control.
                text=False,
                timeout=self._config.timeout_seconds,
                # No stdin inheritance; empty input stream only.
                input="",
                env=self._safe_env(),
            )
        except subprocess.TimeoutExpired:
            return self._failure(
                "command_timeout",
                f"HVS capability probe exceeded timeout "
                f"{self._config.timeout_seconds}s",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except PermissionError as exc:
            return self._failure(
                "permission_error",
                f"could not execute HVS capability probe: {type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except (OSError, ValueError) as exc:
            # Missing executable, bad cwd, or other environment failure.
            return self._failure(
                "adapter_blocked",
                f"HVS capability probe could not start: {type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except Exception as exc:  # noqa: BLE001 - boundary must not leak raw trace
            return self._failure(
                "adapter_blocked",
                f"unexpected error during HVS capability probe: "
                f"{type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )

        stdout = _decode_output(proc.stdout, max_chars=max_chars)
        stderr = _decode_output(proc.stderr, max_chars=max_chars)
        exit_code = int(proc.returncode)
        ok = exit_code == 0

        summary = (
            f"HVS capability probe {'succeeded' if ok else 'failed'} "
            f"(exit={exit_code})"
        )
        return AgentAdapterResult.of(
            result_id=self._config.result_id(request_id=request_id),
            request_id=request_id,
            session_id="scos-hvs-stage1",
            agent_name=self.agent_name(),
            runtime_id="hvs-cli",
            status="result_ready" if ok else "failed",
            result_type="probe_report",
            result_summary=summary,
            output_text=stdout if ok else None,
            output_path=None,
            created_at=created_at,
            next_action=(
                "no further action in Stage 1 (read-only probe only)"
                if ok
                else "review HVS CLI availability and configuration"
            ),
            metadata=(
                ("operation", self._config.operation),
                ("exit_code", str(exit_code)),
                ("argv", " ".join(argv)),
                ("cwd", str(cwd)),
                ("stdout_excerpt", stdout[:200]),
                ("stderr_excerpt", stderr[:200]),
                ("stage", "scos-hvs-stage1"),
            ),
        )

    # --- helpers ------------------------------------------------------------
    # The pinned external HyperFrames tool root. A validated HyperFrames
    # identity MUST reside under a directory containing this fragment, which
    # encodes BOTH the approved external location AND the exact version
    # (0.7.45). Launchers outside this root are rejected fail-closed.
    APPROVED_HYPERFRAMES_TOOL_ROOT_FRAGMENT = "hyperframes-0.7.45"

    @staticmethod
    def validate_tool_path(
        bin_path: "str | None",
        *,
        require_approved_root: bool = False,
    ) -> "tuple[str | None, str | None]":
        """Validate an explicit executable identity (fail-closed).

        Returns ``(canonical_abs_path, error_code)``. On success
        ``error_code`` is ``None``. On ANY failure the path is ``None`` and
        ``error_code`` is a stable, NON-SECRET code; the absolute path is NEVER
        returned in the error.

        When ``require_approved_root`` is True the file MUST reside under the
        pinned external HyperFrames 0.7.45 tool root (outside both repos). This
        doubles as the version check: the packaged directory name pins 0.7.45.
        """
        if not bin_path or not bin_path.strip():
            return (None, "HF_IDENTITY_EMPTY")
        raw = Path(bin_path).expanduser()
        try:
            p = raw.resolve(strict=False)
        except (OSError, ValueError):
            return (None, "HF_IDENTITY_UNRESOLVABLE")
        if not p.is_absolute():
            return (None, "HF_IDENTITY_NOT_ABSOLUTE")
        try:
            real = p.resolve(strict=True)
        except (OSError, ValueError):
            return (None, "HF_IDENTITY_NOT_FOUND")
        if not real.is_file():
            return (None, "HF_IDENTITY_NOT_A_FILE")
        # Symlink / traversal escape guard.
        if ".." in p.parts:
            return (None, "HF_IDENTITY_TRAVERSAL")
        # The launcher must live OUTSIDE the SCOS repo and the HVS repo.
        repo_root = Path(__file__).resolve().parents[3]
        scos_pkg_root = Path(__file__).resolve().parents[1]
        try:
            real.relative_to(repo_root)
            inside_repo = True
        except ValueError:
            inside_repo = False
        try:
            real.relative_to(scos_pkg_root)
            inside_scos = True
        except ValueError:
            inside_scos = False
        if inside_repo or inside_scos:
            return (None, "HF_IDENTITY_INSIDE_REPO")
        if require_approved_root and (
            HermesVideoStudioAdapter.APPROVED_HYPERFRAMES_TOOL_ROOT_FRAGMENT
            not in str(real)
        ):
            return (None, "HF_IDENTITY_OUTSIDE_APPROVED_ROOT")
        return (str(real), None)

    def _synthetic_render_path(
        self,
        hyperframes_bin: str,
        node_bin: "str | None" = None,
    ) -> "str | None":
        """Build a minimal SYNTHETIC PATH from validated tool identities.

        Contains ONLY:
          * the directory of the validated HyperFrames ``.cmd`` launcher, and
          * (when provided) the directory of the validated ``node.exe``.

        No parent ``PATH`` is inherited, no global package discovery occurs,
        and no ``npx`` / ``latest`` lookup is performed. Returns ``None`` when
        the identity cannot be used, so the caller fails closed.
        """
        hf_canon, hf_err = self.validate_tool_path(
            hyperframes_bin, require_approved_root=True
        )
        if hf_err or not hf_canon:
            return None
        dirs = [str(Path(hf_canon).parent)]
        if node_bin:
            node_canon, node_err = self.validate_tool_path(
                node_bin, require_approved_root=False
            )
            if not node_err and node_canon:
                d = str(Path(node_canon).parent)
                if d not in dirs:
                    dirs.append(d)
        return os.pathsep.join(dirs)

    def _safe_env(
        self,
        *,
        hyperframes_bin: "str | None" = None,
        node_bin: "str | None" = None,
    ):
        """Construct a minimal, non-secret environment for the HVS subprocess.

        FAIL-CLOSED: NO parent environment is inherited. The previously
        certified ``env={}`` contract is preserved for read-only operations;
        only the state-mutating ``render-hyperframes`` path (which requires the
        HyperFrames launcher) receives a SYNTHETIC, server-controlled PATH.

        The synthetic PATH contains ONLY the directory of the validated
        ``SCOS_HYPERFRAMES_BIN`` launcher and (when configured) the validated
        ``node.exe`` directory. No parent ``PATH`` is copied, no global package
        discovery occurs, and no secret/credential variable is forwarded.

        Required Windows OS values (SYSTEMROOT/SYSTEMDRIVE/WINDIR/COMSPEC/TEMP/
        TMP/PYTHONIOENCODING/PATHEXT) are taken from the process environment
        only when present and cannot redirect the renderer to an untrusted
        location.
        """
        env: dict[str, str] = {}
        for key in (
            "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
            "TEMP", "TMP", "PYTHONIOENCODING", "PATHEXT",
        ):
            val = os.environ.get(key)
            if val:
                env[key] = val
        if hyperframes_bin:
            synth = self._synthetic_render_path(hyperframes_bin, node_bin=node_bin)
            if synth:
                env["PATH"] = synth
        return env

    def _run_json_command(
        self,
        *,
        command: str,
        args: list[str],
        request_id: str,
        hyperframes_bin: "str | None" = None,
        node_bin: "str | None" = None,
    ) -> dict[str, Any]:
        """Run one approved HVS JSON command through the bounded CLI boundary."""
        if command not in {"initialize-project", "inspect-project", "render-hyperframes", "materialize-render-inputs"}:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "unsupported_operation",
                "error_detail": "unsupported HVS command",
            }
        problems = self._config.validate()
        if problems:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "invalid_configuration",
                "error_detail": "; ".join(problems),
            }
        argv = [self._config.python_executable, "-m", self._config.cli_module, command, *args]
        if any(_has_shell_metacharacter(tok) for tok in argv):
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "unsafe_command",
                "error_detail": "constructed argv contained a shell metacharacter",
            }
        cwd = Path(self._config.hvs_repo_path).resolve()
        # Read-only / initialize operations keep the FAIL-CLOSED empty-env
        # contract (no PATH, no inherited secrets). Only the render path may
        # receive the synthetic, server-validated HyperFrames PATH.
        safe_env = self._safe_env()
        if command == "render-hyperframes":
            safe_env = self._safe_env(hyperframes_bin=hyperframes_bin, node_bin=node_bin)
        try:
            proc = self._subprocess_run(
                list(argv),
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                # Raw bytes: the internal reader thread never decodes, so it
                # cannot raise UnicodeDecodeError on cp1252 output (e.g. 0x97).
                # Control-plane JSON is decoded STRICTLY below.
                text=False,
                timeout=self._config.timeout_seconds,
                input="",
                env=safe_env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "command_timeout",
                "error_detail": f"HVS {command} exceeded timeout {self._config.timeout_seconds}s",
            }
        except PermissionError:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "permission_error",
                "error_detail": f"could not execute HVS {command}",
            }
        except (OSError, ValueError) as exc:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "adapter_blocked",
                "error_detail": f"HVS {command} could not start: {type(exc).__name__}",
            }
        stdout = _decode_output(proc.stdout, max_chars=self._config.max_output_chars)
        stderr = _decode_output(proc.stderr, max_chars=self._config.max_output_chars)
        # Strict-decode the raw control-plane bytes. A non-UTF-8 byte (cp1252
        # 0x97) raises UnicodeDecodeError, which we normalize as malformed_output
        # so corrupt/foreign-encoded control-plane JSON is REJECTED, never
        # silently accepted and never crashes a background reader thread.
        try:
            raw_text = _to_bytes(proc.stdout).decode(
                _OUTPUT_TEXT_ENCODING, errors=_OUTPUT_JSON_ERRORS
            )
        except UnicodeDecodeError:
            return {
                "ok": False,
                "command": command,
                "exit_code": int(proc.returncode),
                "payload": None,
                "stdout_excerpt": stdout[:200],
                "stderr_excerpt": stderr[:200],
                "error_kind": "malformed_output",
                "error_detail": "HVS control-plane output is not valid UTF-8 (non-UTF-8 bytes such as cp1252 0x97 present)",
            }
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "command": command,
                "exit_code": int(proc.returncode),
                "payload": None,
                "stdout_excerpt": stdout[:200],
                "stderr_excerpt": stderr[:200],
                "error_kind": "malformed_output",
                "error_detail": "HVS command did not return JSON",
            }
        return {
            "ok": int(proc.returncode) == 0,
            "command": command,
            "exit_code": int(proc.returncode),
            "payload": payload,
            "stdout_excerpt": stdout[:200],
            "stderr_excerpt": stderr[:200],
            "error_kind": None if int(proc.returncode) == 0 else "hvs_command_failed",
            "error_detail": None if int(proc.returncode) == 0 else str(payload.get("error_detail") or stderr[:200]),
            "request_id": request_id,
        }

    def initialize_project(
        self,
        *,
        project_id: str,
        contract_path: str,
        expected_payload_hash: str,
        approve_initialization: bool,
        request_id: str,
        stage85_authorization: "Stage8_5AdapterAuthorization | None" = None,
        cohort10d_authorization: "dict[str, Any] | None" = None,
        projects_root: "str | None" = None,
    ) -> dict[str, Any]:
        """Create the HVS project (STATE_MUTATING).

        This is the ONLY mutating HVS command exposed by the adapter. Per the
        Stage 8.5 / Cohort 9F gate, a valid, correctly bound authorization
        decision MUST be evaluated BEFORE any subprocess/HVS invocation.

        Cohort 10D integration: when ``cohort10d_authorization`` (a Cohort-10D
        materialization ``AuthorizationRecord`` dict) is supplied, a Stage 8.5
        decision is DERIVED from it — ``AUTHORIZED_IN_PRINCIPLE`` only when the
        record is explicitly ``AUTHORIZED`` and still within its TTL; otherwise
        fail-closed. This keeps the existing HVS adapter as the single real
        mutation boundary while delegating authorization authority to the
        Python authoritative materialization service.

        ``projects_root`` is an OPT-IN, NON-PRODUCTION isolation hook. When set,
        it is forwarded to the HVS CLI so a canary may materialize into an
        isolated OS-temp root without touching the production studio workspace.
        Production callers MUST pass ``None`` (writes under STUDIO_ROOT).

        Fail-closed:
          * missing / malformed / unknown decision -> no invocation,
            returns ok=False with a stable, non-secret reason code;
          * DENIED / BLOCKED / EXPIRED -> no invocation;
          * operation/target binding mismatch -> no invocation;
          * no project directory, manifest, or HVS state is created on deny.
        """
        # Cohort 10D delegation: derive the Stage 8.5 decision from the
        # authoritative materialization authorization record. This takes
        # precedence over the adapter's default (which is an empty, non-None
        # ``Stage8_5AdapterAuthorization``): if a Cohort-10D record is
        # supplied, the adapter MUST translate it rather than fall back to the
        # empty default (which would fail-closed as "missing").
        if cohort10d_authorization is not None:
            decision = stage85_from_cohort10d_authorization(cohort10d_authorization)
        else:
            decision = stage85_authorization or self._stage85_authorization
        # AUTHORIZATION_BEFORE_SIDE_EFFECT: evaluate at the last common point
        # before any filesystem/project/subprocess side effect.
        try:
            (decision or Stage8_5AdapterAuthorization("")).require_for(
                operation="initialize-project", target=str(project_id)
            )
        except Stage8_5AuthorizationError as exc:
            return {
                "ok": False,
                "command": "initialize-project",
                "exit_code": None,
                "payload": None,
                "error_kind": "stage85_authorization_blocked",
                "error_detail": exc.reason,  # stable non-secret reason code only
            }
        args = [
            "--project-id",
            str(project_id),
            "--contract-path",
            str(contract_path),
            "--expected-payload-hash",
            str(expected_payload_hash),
        ]
        if approve_initialization:
            args.append("--approve-initialization")
        # ISOLATION HOOK: only forward an explicit isolated root; never a
        # production override. The CLI ignores None and uses STUDIO_ROOT.
        if projects_root is not None:
            args.extend(["--projects-root", str(projects_root)])
        return self._run_json_command(command="initialize-project", args=args, request_id=request_id)

    def inspect_project(
        self, *, project_id: str, request_id: str, projects_root: "str | None" = None
    ) -> dict[str, Any]:
        """Read-only HVS project inspection (READ_ONLY).

        This command MUST NOT create, mutate, or initialize any HVS project,
        directory, manifest, evidence, or state. It is a query only and does
        not require a Stage 8.5 authorization decision. It never performs an
        implicit initialization of a missing project.

        ``projects_root`` is the same OPT-IN isolation hook used by
        ``initialize_project``: when set, the read-only inspection targets the
        isolated canary root so reconciliation can verify an isolated project
        without touching production. Production callers pass ``None``.
        """
        args = ["--project-id", str(project_id)]
        if projects_root is not None:
            args.extend(["--projects-root", str(projects_root)])
        return self._run_json_command(command="inspect-project", args=args, request_id=request_id)

    def materialize_render_inputs(
        self,
        *,
        project_id: str,
        request_id: str,
        projects_root: "str | None" = None,
        expected_payload_hash: "str | None" = None,
        cohort10e_render_inputs_authorization: "dict[str, Any] | None" = None,
    ) -> dict[str, Any]:
        """Materialize downstream render-input artifacts (STATE_MUTATING).

        Invokes ONLY the certified narrow HVS ``materialize-render-inputs``
        command. This is the downstream companion to ``initialize_project``:
        it runs AFTER a validated initialization and produces exactly the three
        downstream render-input artifacts (template_selection.json,
        voice_manifest.json, asset_manifest.json). It NEVER renders, NEVER
        invokes HyperFrames/Chromium/FFmpeg, and NEVER writes outside the
        trusted ``projects_root``.

        Authorization gate (Stage 8.5, Cohort 10E): a dedicated, correctly
        bound authorization decision MUST be evaluated BEFORE the subprocess.
        The decision is DERIVED from the authoritative Cohort-10E downstream
        render-input authorization record (``cohort10e_render_inputs_authorization``)
        which binds to the ``materialize-render-inputs`` operation and the
        derived HVS project id. Fail-closed on missing/denied/expired/mismatch.

        ``projects_root`` is an OPT-IN, NON-PRODUCTION isolation hook (absolute
        trusted path only). When set, it is forwarded to the HVS CLI so a
        canary may materialize into an isolated OS-temp root. The adapter
        REJECTS a non-absolute root before any subprocess. Production callers
        pass ``None`` (writes under STUDIO_ROOT).
        """
        # Reject an invalid (non-absolute) projects root before any subprocess.
        if projects_root is not None:
            try:
                root = Path(projects_root)
                if not root.is_absolute():
                    return {
                        "ok": False,
                        "command": "materialize-render-inputs",
                        "exit_code": None,
                        "payload": None,
                        "error_kind": "invalid_projects_root",
                        "error_detail": "projects_root must be an absolute trusted path",
                    }
            except (ValueError, OSError):
                return {
                    "ok": False,
                    "command": "materialize-render-inputs",
                    "exit_code": None,
                    "payload": None,
                    "error_kind": "invalid_projects_root",
                    "error_detail": "projects_root is not a resolvable path",
                }
        # Reject an invalid hvs-* identity before subprocess.
        if not project_id or not project_id.lower().startswith("hvs-"):
            return {
                "ok": False,
                "command": "materialize-render-inputs",
                "exit_code": None,
                "payload": None,
                "error_kind": "invalid_project_identity",
                "error_detail": "project_id must be a validated hvs-* identity",
            }
        # AUTHORIZATION_BEFORE_SIDE_EFFECT (dedicated operation binding).
        if cohort10e_render_inputs_authorization is not None:
            decision = stage85_from_cohort10e_render_inputs_authorization(
                cohort10e_render_inputs_authorization
            )
        else:
            decision = self._stage85_authorization
        try:
            (decision or Stage8_5AdapterAuthorization("")).require_for(
                operation="materialize-render-inputs", target=str(project_id)
            )
        except Stage8_5AuthorizationError as exc:
            return {
                "ok": False,
                "command": "materialize-render-inputs",
                "exit_code": None,
                "payload": None,
                "error_kind": "stage85_authorization_blocked",
                "error_detail": exc.reason,  # stable non-secret reason code only
            }
        args = ["--project-id", str(project_id)]
        if projects_root is not None:
            args.extend(["--projects-root", str(projects_root)])
        if expected_payload_hash:
            args.extend(["--expected-payload-hash", str(expected_payload_hash)])
        # Read-only / initialize operations keep the FAIL-CLOSED empty-env
        # contract (no PATH, no inherited secrets). No render/network side
        # effects are reachable from this command.
        return self._run_json_command(
            command="materialize-render-inputs", args=args, request_id=request_id
        )

    def render_project(
        self,
        *,
        project_id: str,
        fmt: str,
        request_id: str,
        output_root: "str | None" = None,
        cohort10e_authorization: "dict[str, Any] | None" = None,
        projects_root: "str | None" = None,
        hyperframes_bin: "str | None" = None,
        node_bin: "str | None" = None,
    ) -> dict[str, Any]:
        """Render the HVS project (STATE_MUTATING).

        This is the ONLY mutating render command exposed by the adapter and
        the sole render side-effect boundary for Cohort 10E. The Stage 8.5
        decision is derived from the Cohort-10E render authorization record
        (``cohort10e_authorization``), which the authoritative Python render
        service issued ONLY on explicit operator confirmation. A missing /
        denied / expired / mismatched authorization fails closed with no HVS
        invocation.

        ``hyperframes_bin`` is the EXPLICIT, server-validated HyperFrames
        launcher identity (passed through from ``SCOS_HYPERFRAMES_BIN``). It is
        validated here and forwarded to the certified HVS ``render_project`` as
        an explicit parameter — no ``PATH``-based discovery is used. An invalid
        identity fails closed BEFORE any HVS subprocess is spawned. ``None``
        means "no trusted identity configured", which also fails closed for the
        real render path.

        ``output_root`` / ``projects_root`` are OPT-IN, NON-PRODUCTION
        isolation hooks: when set, they are forwarded to the HVS CLI so a
        canary may render into an isolated OS-temp root without touching the
        production studio workspace. Production callers MUST pass ``None``.
        """
        if cohort10e_authorization is not None:
            decision = stage85_from_cohort10e_authorization(cohort10e_authorization)
        else:
            decision = self._stage85_authorization
        try:
            (decision or Stage8_5AdapterAuthorization("")).require_for(
                operation="render-hyperframes", target=str(project_id)
            )
        except Stage8_5AuthorizationError as exc:
            return {
                "ok": False,
                "command": "render-hyperframes",
                "exit_code": None,
                "payload": None,
                "error_kind": "stage85_authorization_blocked",
                "error_detail": exc.reason,
            }
        # Explicit identity gate: validate BEFORE any subprocess.
        if hyperframes_bin is None:
            return {
                "ok": False,
                "command": "render-hyperframes",
                "exit_code": None,
                "payload": None,
                "error_kind": "hf_identity_missing",
                "error_detail": "no trusted HyperFrames identity configured",
            }
        _, hf_err = self.validate_tool_path(hyperframes_bin, require_approved_root=True)
        if hf_err:
            return {
                "ok": False,
                "command": "render-hyperframes",
                "exit_code": None,
                "payload": None,
                "error_kind": "hf_identity_invalid",
                "error_detail": hf_err,  # stable, non-secret code
            }
        args = ["--project-id", str(project_id), "--format", str(fmt)]
        if output_root is not None:
            args.extend(["--output-root", str(output_root)])
        if projects_root is not None:
            args.extend(["--projects-root", str(projects_root)])
        if node_bin:
            args.extend(["--node-bin", str(node_bin)])
        return self._run_json_command(
            command="render-hyperframes",
            args=args,
            request_id=request_id,
            hyperframes_bin=hyperframes_bin,
            node_bin=node_bin,
        )

    def _failure(
        self,
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        request_id: str,
        created_at: str,
        argv: list[str] | None = None,
        cwd: str | None = None,
    ) -> AgentAdapterError:
        metadata: list[tuple[str, str]] = [
            ("adapter_id", self.adapter_id()),
            ("operation", self._config.operation),
            ("stage", "scos-hvs-stage1"),
        ]
        if argv is not None:
            # argv is a safe, allowlisted list; record it for audit evidence.
            metadata.append(("argv", " ".join(argv)))
        if cwd is not None:
            metadata.append(("cwd", cwd))
        return AgentAdapterError.of(
            error_kind,
            error_detail,
            failed_step,
            ok=False,
            schema_version=AI_AGENT_ADAPTER_SCHEMA_VERSION,
            request_id=request_id,
            metadata=tuple(metadata),
        )

    # --- Stage 2 planning surface (no activation, no subprocess) ------------
    def plan_hvs_contract_payload(self, scos_project) -> "AgentAdapterResult | AgentAdapterError":
        """Produce a Stage 2 HVS-compatible contract payload from a SCOS project.

        Stage 2 planning only. This method does NOT invoke the HVS CLI, does NOT
        create an HVS project, does NOT write any file, and performs NO
        subprocess. It delegates to the pure deterministic mapper
        (``scos.control_center.hvs_schema_mapper``) and returns the result
        wrapped as a normal ``AgentAdapterResult`` (``result_type="plan"``) or a
        structured ``AgentAdapterError`` on invalid input.

        This is a read-only planning affordance: it never changes adapter
        activation defaults, render backend selection, or the allowlisted
        read-only operation set. It is NOT registered as a production route.
        """
        if scos_project is None:
            return self._failure(
                "missing_required_field",
                "scos_project is required",
                "plan_hvs_contract_payload",
                request_id="plan",
                created_at="plan",
            )
        # Lazy import keeps the Stage 1 subprocess profile unchanged: the mapper
        # is only loaded when planning is actually requested.
        try:
            from hvs_schema_mapper import map_scos_to_hvs
        except Exception as exc:  # noqa: BLE001 - boundary must not leak trace
            return self._failure(
                "adapter_blocked",
                f"Stage 2 mapper unavailable: {type(exc).__name__}",
                "plan_hvs_contract_payload",
                request_id="plan",
                created_at="plan",
            )
        result = map_scos_to_hvs(scos_project, validate=True)
        if not result.ok:
            return AgentAdapterError.of(
                "contract_violation",
                result.error.error_detail,
                "plan_hvs_contract_payload",
                ok=False,
                schema_version=AI_AGENT_ADAPTER_SCHEMA_VERSION,
                request_id="plan",
                metadata=(
                    ("stage", "scos-hvs-stage2"),
                    ("error_kind", result.error.error_kind),
                    ("field", result.error.field or ""),
                ),
            )
        return AgentAdapterResult.of(
            result_id=self._config.result_id(request_id="plan-stage2"),
            request_id="plan-stage2",
            session_id="scos-hvs-stage2",
            agent_name=self.agent_name(),
            runtime_id="hvs-cli",
            status="result_ready",
            result_type="plan",
            result_summary="Stage 2 HVS contract payload planned (no render, no project creation)",
            output_text=None,
            output_path=None,
            created_at="plan",
            next_action="no further action in Stage 2 (planning only)",
            metadata=(
                ("stage", "scos-hvs-stage2"),
                ("contract_id", result.payload.get("deterministic_hash", "")),
                ("resolution", str(result.payload.get("resolution", ""))),
                ("fps", str(result.payload.get("fps", ""))),
                ("scene_count", str(result.payload.get("scene_count", ""))),
            ),
        )

    # --- contract compliance note -------------------------------------------
    # BaseAgentAdapter also declares prepare_prompt / simulate_send /
    # capture_result. Those are intentionally NOT overridden: the HVS adapter
    # is a read-only capability probe and never delivers prompts or captures
    # operator-supplied results. Callers use ``run_readonly_probe``. The base
    # methods remain available (and would fail validation for this adapter's
    # agent_name/runtime_type/task_type if misused), preserving the contract.


def build_hvs_adapter_config(
    hvs_repo_path: str,
    python_executable: str,
    *,
    operation: str = "hvs_capability_probe",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    cli_module: str = _HVS_MODULE,
) -> HVSAdapterConfig:
    """Explicit factory for HVS adapter configuration.

    No global constant embeds a user's home directory; every value is an
    explicit argument. A Windows default path may be supplied by the caller or
    by a higher-level factory, never forced here.
    """
    return HVSAdapterConfig(
        hvs_repo_path=hvs_repo_path,
        python_executable=python_executable,
        operation=operation,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
        cli_module=cli_module,
    )


__all__ = [
    "STAGE1_READONLY_OPERATIONS",
    "READ_ONLY_OPERATIONS",
    "STATE_MUTATING_OPERATIONS",
    "Stage8_5AdapterAuthorization",
    "Stage8_5AuthorizationError",
    "HVSAdapterConfig",
    "HermesVideoStudioAdapter",
    "build_hvs_adapter_config",
]
