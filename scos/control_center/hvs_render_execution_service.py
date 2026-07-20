"""Cohort 10E — controlled HVS project render execution authority.

Orchestrates the exact side-effect sequence (Cohort 10E §7) from an
authoritative, explicit operator confirmation to a single, controlled HVS
render of one trusted materialized project, then validates the resulting
artifact and projects a browser-safe descriptor.

Design boundaries (enforced, not implied):
  * This module is stdlib-only. It NEVER imports hvs.*, NEVER spawns a
    subprocess, NEVER reaches the network. The only HVS sink is the
    injected ``hvs_render`` callable, which canary wiring points at the
    REAL ``HermesVideoStudioAdapter.render_project`` (sole render boundary).
  * No HVS/filesystem mutation occurs before authorization + single-use
    capability consumption. Every rejection before that point leaves
    ``render_calls == 0`` and the isolated output root untouched.
  * The authorization is evaluated and the single-use capability is
    consumed atomically BEFORE the HVS render boundary is crossed.
  * An unknown outcome (timeout / lost response after a possible render
    start) is recorded as RENDER_OUTCOME_UNKNOWN and is NEVER retried
    automatically.
  * Reconciliation is read-only and may classify but never re-render.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .hvs_render_plan_models import (  # noqa: E402
    DECISION_AUTHORIZED,
    DECISION_DENIED,
    DECISION_DESTINATION_MISMATCH,
    DECISION_EXPIRED,
    DECISION_MALFORMED,
    DECISION_PLAN_MISMATCH,
    DECISION_REVISION_MISMATCH,
    DECISION_STALE,
    DEFAULT_TTL_SECONDS,
    ERR_AUTHORIZATION_CONSUMED,
    ERR_AUTHORIZATION_DESTINATION_MISMATCH,
    ERR_AUTHORIZATION_EXPIRED,
    ERR_AUTHORIZATION_MALFORMED,
    ERR_AUTHORIZATION_MISSING,
    ERR_AUTHORIZATION_OPERATION_MISMATCH,
    ERR_AUTHORIZATION_PLAN_MISMATCH,
    ERR_AUTHORIZATION_REVISION_MISMATCH,
    ERR_AUTHORIZATION_STALE,
    ERR_ARTIFACT_NOT_FOUND,
    ERR_ARTIFACT_VALIDATION_FAILED,
    ERR_CAPABILITY_CONSUMED,
    ERR_CAPABILITY_EXPIRED,
    ERR_CAPABILITY_MALFORMED,
    ERR_CAPABILITY_MISSING,
    ERR_CAPABILITY_OPERATION_MISMATCH,
    ERR_CAPABILITY_PLAN_MISMATCH,
    ERR_CAPABILITY_REVISION_MISMATCH,
    ERR_CAPABILITY_DESTINATION_MISMATCH,
    ERR_DISK_CAPACITY_INSUFFICIENT,
    ERR_HVS_PROJECT_NOT_FOUND,
    ERR_HVS_RENDER_FAILED,
    ERR_INFLIGHT_ATTEMPT,
    ERR_MATERIALIZATION_NOT_CONFIRMED,
    ERR_PREREQUISITE_UNMET,
    ERR_PROJECT_NOT_READY,
    ERR_PROJECT_REVISION_CONFLICT,
    ERR_RENDER_ALREADY_ACTIVE,
    ERR_RENDER_PLAN_MISMATCH,
    ERR_RENDER_PROFILE_UNSUPPORTED,
    ERR_RECONCILE_REQUIRED,
    ERR_TOOLCHAIN_UNAVAILABLE,
    HvsRenderAttempt,
    HvsRenderAuthorization,
    HvsRenderCapability,
    HvsRenderPlan,
    OPERATION_RENDER_HVS_PROJECT,
    RENDER_PROFILES,
    RENDER_SCHEMA_VERSION,
    RECONCILED_FAILED_CONFIRMED,
    RECONCILED_RECONCILE_REQUIRED,
    RECONCILED_STILL_UNKNOWN,
    RECONCILED_SUCCEEDED,
    RECONCILED_ATTEMPT_NOT_FOUND,
    RECONCILED_INSPECT_FAILED,
    STATE_RENDER_AUTHORIZATION_REQUIRED,
    STATE_RENDER_AUTHORIZED,
    STATE_ARTIFACT_DISCOVERED,
    STATE_ARTIFACT_VALIDATED,
    STATE_RENDER_FAILED_CONFIRMED,
    STATE_RENDER_NOT_REQUESTED,
    STATE_RENDER_OUTCOME_UNKNOWN,
    STATE_RENDER_RECONCILIATION_REQUIRED,
    STATE_RENDER_RUNNING,
    STATE_RENDER_STARTING,
    STATE_RENDER_SUCCEEDED,
    is_supported_render_profile,
)
from .hvs_render_attempt_store import RenderAttemptStore  # noqa: E402

# Forbidden output roots (no production HVS workspace, no SCOS production
# data, no repository root may ever be the render output root).
_FORBIDDEN_OUTPUT_PREFIXES = (
    "C:/Workspace/hermes-video-studio",
    "C:\\Workspace\\hermes-video-studio",
    "C:/Workspace/super-creator-os",
    "C:\\Workspace\\super-creator-os",
    "memory/database.json",
    "memory/runtime/control-center",
)

# Materialization truth states that permit a render (Cohort 10D §6.2).
_MATERIALIZATION_READY_STATES = ("HVS_PROJECT_MATERIALIZED",)


@dataclass
class RenderResult:
    ok: bool
    state: str
    attempt_id: Optional[str] = None
    authorization_id: Optional[str] = None
    capability_id: Optional[str] = None
    render_attempt_id: Optional[str] = None
    render_calls: int = 0
    hvs_calls: int = 0
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    persisted_result: Optional[dict[str, Any]] = None
    plan: Optional[HvsRenderPlan] = None
    artifact: Optional[dict[str, Any]] = None

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "state": self.state,
            "attempt_id": self.render_attempt_id or self.attempt_id,
            "authorization_id": self.authorization_id,
            "capability_id": self.capability_id,
            "render_calls": self.render_calls,
            "hvs_calls": self.hvs_calls,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "persisted_result": self.persisted_result,
            "artifact": self.artifact,
        }


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalized_hvs_project_name(project_id: str) -> str:
    """Deterministic, HVS-safe project name from a SCOS project id."""
    suffix = project_id
    if suffix.startswith("spp-"):
        suffix = suffix[len("spp-"):]
    return f"hvs-{suffix}"


def _default_expires_at(issued_at: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    base = issued_at.replace("Z", "")
    try:
        from datetime import datetime, timezone

        dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f")
        dt = dt.replace(tzinfo=timezone.utc)
        exp = dt.timestamp() + ttl_seconds
        return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, TypeError):
        return f"{issued_at}+ttl"


def is_safe_output_root(output_root_identity: str) -> bool:
    """Return True only when the output root is cohort-owned and isolated."""
    d = (output_root_identity or "").replace("\\", "/").rstrip("/")
    if not d:
        return False
    if ".." in d.split("/"):
        return False
    for forbidden in _FORBIDDEN_OUTPUT_PREFIXES:
        if d.startswith(forbidden.replace("\\", "/")):
            return False
    if "/AppData/Local/Temp/" not in d and d.startswith("C:/Workspace"):
        return False
    return True


# --------------------------------------------------------------------------
# Render plan construction (Cohort 10E §6.1 / §6.4)
# --------------------------------------------------------------------------

def build_render_plan(
    *,
    project_id: str,
    project_revision: int,
    materialization_attempt_id: str,
    materialization_plan_hash: str,
    render_profile_id: str,
    output_root_identity: str,
    now_iso: str,
) -> HvsRenderPlan:
    """Build the deterministic, reviewable render plan.

    The plan contains NO credentials, NO secrets, NO arbitrary shell
    commands, NO browser-supplied filesystem destination, NO unvalidated
    absolute asset paths, NO publish command, and NO external URL fetch.
    It declares the expected render output (filename + relative path) only,
    derived from the versioned render profile.
    """
    if not is_supported_render_profile(render_profile_id):
        raise ValueError(f"unsupported render profile: {render_profile_id!r}")
    profile = RENDER_PROFILES[render_profile_id]
    hvs_name = normalized_hvs_project_name(project_id)
    expected_filename = f"{hvs_name}.{profile.resolution}.{profile.video_codec}.mp4"
    expected_relative_path = f"render/{hvs_name}/{expected_filename}"
    profile_metadata = {
        "scos_project_id": project_id,
        "hvs_project_name": hvs_name,
        "render_profile_id": render_profile_id,
        "render_profile_version": profile.version,
        "resolution": profile.resolution,
        "width": profile.width,
        "height": profile.height,
        "fps": profile.fps,
        "video_codec": profile.video_codec,
        "pixel_format": profile.pixel_format,
    }
    forbidden_operations = (
        "publish",
        "upload",
        "export-project",
        "import-media",
        "create-render-pack",
        "verify-real-render-output",
        "render-hyperframes",
    )
    plan = HvsRenderPlan(
        plan_schema_version=RENDER_SCHEMA_VERSION,
        project_id=project_id,
        project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id,
        hvs_project_name=hvs_name,
        output_root_identity=output_root_identity,
        profile_metadata=profile_metadata,
        expected_output_filename=expected_filename,
        expected_output_relative_path=expected_relative_path,
        forbidden_operations=forbidden_operations,
        plan_hash="",
    )
    # Authoritative server-side plan hash. Deterministic over the
    # authorization-relevant canonical content (excluding the hash field
    # itself). Never trusts the browser-supplied value, which is empty during
    # a read-only projection. Same canonical plan -> same hash; an
    # authorization-relevant plan change -> different hash.
    _content = {k: v for k, v in plan.canonical_content().items() if k != "materialization_plan_hash"}
    _plan_hash = _sha256_hex(_canonical_json(_content))
    return HvsRenderPlan(
        **{**plan.to_dict(), "materialization_plan_hash": _plan_hash, "plan_hash": _plan_hash}
    )


# --------------------------------------------------------------------------
# Readiness gate (Cohort 10E §6.3) — prove every precondition or fail closed
# --------------------------------------------------------------------------

def evaluate_readiness(
    *,
    materialization_state: str,
    project_revision: int,
    expected_revision: int,
    materialization_plan_hash: str,
    expected_materialization_plan_hash: str,
    render_profile_id: str,
    hvs_project_exists: bool,
    output_root_identity: str,
    output_target_conflicts: bool,
    toolchain_available: bool,
    browser_runtime_available: bool,
    disk_threshold_met: bool,
    has_active_render: bool,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if materialization_state not in _MATERIALIZATION_READY_STATES:
        blockers.append(ERR_MATERIALIZATION_NOT_CONFIRMED)
    if project_revision != expected_revision:
        blockers.append(f"revision_conflict:{expected_revision}!={project_revision}")
    if materialization_plan_hash != expected_materialization_plan_hash:
        blockers.append("materialization_plan_hash_mismatch")
    if not is_supported_render_profile(render_profile_id):
        blockers.append(ERR_RENDER_PROFILE_UNSUPPORTED)
    if not hvs_project_exists:
        blockers.append(ERR_HVS_PROJECT_NOT_FOUND)
    if not is_safe_output_root(output_root_identity):
        blockers.append(ERR_AUTHORIZATION_DESTINATION_MISMATCH)
    if output_target_conflicts:
        blockers.append("OUTPUT_TARGET_CONFLICT")
    if not toolchain_available:
        blockers.append(ERR_TOOLCHAIN_UNAVAILABLE)
    if not browser_runtime_available:
        blockers.append("BROWSER_RUNTIME_UNAVAILABLE")
    if not disk_threshold_met:
        blockers.append(ERR_DISK_CAPACITY_INSUFFICIENT)
    if has_active_render:
        blockers.append(ERR_RENDER_ALREADY_ACTIVE)
    return (not blockers, tuple(sorted(set(blockers))))


# --------------------------------------------------------------------------
# Authorization issuance (Cohort 10E §6.2) — ONLY after explicit confirmation
# --------------------------------------------------------------------------

def issue_authorization(
    *,
    store: RenderAttemptStore,
    project_id: str,
    project_revision: int,
    materialization_attempt_id: str,
    materialization_plan_hash: str,
    render_profile_id: str,
    output_root_identity: str,
    operator_id: str,
    confirmed: bool,
    now_iso: str,
    authorization_id: str,
    nonce: str,
) -> tuple[Optional[HvsRenderAuthorization], Optional[str], Optional[str]]:
    """Issue an immutable, bound authorization.

    Returns (authorization, decision, error_code). The decision is
    ``AUTHORIZED`` only when the operator explicitly confirmed AND the render
    profile is supported AND the output root is safe. Otherwise a
    non-authorized decision is returned (fail-closed) and NOTHING is
    persisted as AUTHORIZED.
    """
    plan = build_render_plan(
        project_id=project_id,
        project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id,
        output_root_identity=output_root_identity,
        now_iso=now_iso,
    )
    # Fail-closed: a non-empty supplied plan hash must match the server's
    # authoritative canonical hash. The projection is the only legitimate
    # source of the hash; any conflicting/stale value is rejected.
    if materialization_plan_hash and materialization_plan_hash != plan.materialization_plan_hash:
        return (None, DECISION_DENIED, "PLAN_HASH_MISMATCH")
    decision = DECISION_DENIED if not confirmed else DECISION_AUTHORIZED
    auth = HvsRenderAuthorization(
        schema_version=RENDER_SCHEMA_VERSION,
        authorization_id=authorization_id,
        project_id=project_id,
        project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id,
        render_plan_hash=plan.plan_hash,
        output_root_identity=output_root_identity,
        issued_at=now_iso,
        expires_at=_default_expires_at(now_iso),
        issued_by=operator_id,
        decision=decision,
        nonce=nonce,
    )
    validation = auth.validate()
    if validation:
        return (auth, DECISION_MALFORMED, ERR_AUTHORIZATION_MALFORMED)
    store.put_authorization(auth)
    err = None if confirmed else ERR_PREREQUISITE_UNMET
    return (auth, decision, err)


# --------------------------------------------------------------------------
# Authorization / capability evaluation (fail closed)
# --------------------------------------------------------------------------

def _evaluate_authorization(
    auth: Optional[HvsRenderAuthorization],
    *,
    project_id: str,
    project_revision: int,
    materialization_attempt_id: str,
    materialization_plan_hash: str,
    render_profile_id: str,
    render_plan_hash: str,
    output_root_identity: str,
    now_iso: str,
) -> Optional[str]:
    if auth is None:
        return ERR_AUTHORIZATION_MISSING
    problems = auth.validate()
    if problems:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.decision != DECISION_AUTHORIZED:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.operation() != OPERATION_RENDER_HVS_PROJECT:
        return ERR_AUTHORIZATION_OPERATION_MISMATCH
    if auth.project_id != project_id:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.project_revision != project_revision:
        return ERR_AUTHORIZATION_REVISION_MISMATCH
    if auth.materialization_attempt_id != materialization_attempt_id:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.materialization_plan_hash != materialization_plan_hash:
        return ERR_AUTHORIZATION_PLAN_MISMATCH
    if auth.render_profile_id != render_profile_id:
        return ERR_RENDER_PROFILE_UNSUPPORTED
    if auth.render_plan_hash != render_plan_hash:
        return ERR_RENDER_PLAN_MISMATCH
    if auth.output_root_identity != output_root_identity:
        return ERR_AUTHORIZATION_DESTINATION_MISMATCH
    if auth.expires_at < now_iso:
        return ERR_AUTHORIZATION_EXPIRED
    return None


def _evaluate_capability(
    cap: Optional[HvsRenderCapability],
    *,
    project_id: str,
    project_revision: int,
    materialization_attempt_id: str,
    materialization_plan_hash: str,
    render_profile_id: str,
    render_plan_hash: str,
    output_root_identity: str,
    now_iso: str,
) -> Optional[str]:
    if cap is None:
        return ERR_CAPABILITY_MISSING
    problems = cap.validate()
    if problems:
        return ERR_CAPABILITY_MALFORMED
    if cap.operation != OPERATION_RENDER_HVS_PROJECT:
        return ERR_CAPABILITY_OPERATION_MISMATCH
    if cap.project_id != project_id:
        return ERR_CAPABILITY_MALFORMED
    if cap.project_revision != project_revision:
        return ERR_CAPABILITY_REVISION_MISMATCH
    if cap.materialization_attempt_id != materialization_attempt_id:
        return ERR_CAPABILITY_MALFORMED
    if cap.materialization_plan_hash != materialization_plan_hash:
        return ERR_CAPABILITY_PLAN_MISMATCH
    if cap.render_profile_id != render_profile_id:
        return ERR_RENDER_PROFILE_UNSUPPORTED
    if cap.render_plan_hash != render_plan_hash:
        return ERR_RENDER_PLAN_MISMATCH
    if cap.output_root_identity != output_root_identity:
        return ERR_CAPABILITY_DESTINATION_MISMATCH
    if cap.is_expired(now_iso=now_iso):
        return ERR_CAPABILITY_EXPIRED
    return None


# --------------------------------------------------------------------------
# Render orchestration (Cohort 10E §7, §11)
# --------------------------------------------------------------------------

# Signature of the injected HVS render callable: returns the real dict shape
# {"ok", "command", "exit_code", "payload", "output_relative_path", ...}.
HvsRenderCallable = Callable[..., dict[str, Any]]
HvsInspectorCallable = Callable[..., dict[str, Any]]
HvsArtifactValidator = Callable[..., dict[str, Any]]


def render(
    *,
    store: RenderAttemptStore,
    project_id: str,
    project_revision: int,
    materialization_attempt_id: str,
    materialization_plan_hash: str,
    render_profile_id: str,
    output_root_identity: str,
    projects_root_identity: str,
    physical_output_root_identity: Optional[str] = None,
    authorization: HvsRenderAuthorization,
    capability_id: str,
    attempt_id: str,
    operator_id: str,
    now_iso: str,
    hvs_render: HvsRenderCallable,
    hvs_inspector: HvsInspectorCallable,
    artifact_validator: HvsArtifactValidator,
    timeout_during_invoke: bool = False,
) -> RenderResult:
    """Execute the controlled render sequence.

    Exactly ONE HVS render call may occur, guarded by single-use capability
    consumption. Any rejection before that point returns with
    ``render_calls == 0`` and the isolated output root untouched. An unknown
    outcome is recorded and never retried automatically.
    """
    plan = build_render_plan(
        project_id=project_id, project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id, output_root_identity=output_root_identity,
        now_iso=now_iso,
    )

    physical_output_root = physical_output_root_identity or output_root_identity

    auth_err = _evaluate_authorization(
        authorization, project_id=project_id, project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id, render_plan_hash=plan.plan_hash,
        output_root_identity=output_root_identity, now_iso=now_iso,
    )
    if auth_err is not None:
        return RenderResult(
            ok=False, state=STATE_RENDER_AUTHORIZATION_REQUIRED,
            authorization_id=authorization.authorization_id if authorization else None,
            capability_id=capability_id, render_calls=0, hvs_calls=0,
            outcome="rejected", error_code=auth_err,
            error_detail="authorization did not permit render", plan=plan,
        )

    existing_cap = store.get_capability(capability_id)
    if existing_cap is not None and existing_cap.is_consumed():
        return RenderResult(
            ok=False, state=STATE_RENDER_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_CAPABILITY_CONSUMED,
            error_detail="capability already consumed (exact replay contained)", plan=plan,
        )

    # --- Render-tree existence gate (Cohort 10F.1 root-cause repair) --------
    # The render-ready HVS project tree MUST exist under the SAME projects root
    # the execute request will hand to the renderer, or the attempt must be
    # fail-closed BEFORE the HVS render boundary is crossed (render_calls=0,
    # hvs_calls=0). Without this gate, a missing/never-materialized project
    # (e.g. an isolated canary root with no initialized hvs-<id>) reaches the
    # real renderer, which fails deep inside the HVS subprocess with a
    # non-actionable RENDER_START_FAILED and a truthful-but-unhelpful
    # "project not found" surfaced only after a render call was already made.
    # The check uses the read-only inspector (no create/initialize). The
    # inspector root is the execute-time projects_root_identity; the
    # normalized hvs-* name is the immutable destination identity.
    try:
        existence_view = hvs_inspector(
            project_id=normalized_hvs_project_name(project_id), request_id=attempt_id,
            projects_root=projects_root_identity,
        )
    except Exception:
        existence_view = None
    project_exists = bool(existence_view and existence_view.get("exists"))
    if not project_exists:
        return RenderResult(
            ok=False, state=STATE_RENDER_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_HVS_PROJECT_NOT_FOUND,
            error_detail=(
                "render-ready HVS project tree absent at the certified projects root; "
                "render not invoked"
            ),
            plan=plan,
        )

    cap = HvsRenderCapability(
        schema_version=RENDER_SCHEMA_VERSION, capability_id=capability_id,
        authorization_id=authorization.authorization_id, project_id=project_id,
        project_revision=project_revision, materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash, render_profile_id=render_profile_id,
        render_plan_hash=plan.plan_hash, output_root_identity=output_root_identity,
        issued_at=now_iso, expires_at=_default_expires_at(now_iso),
        consumed_at=None, operation=OPERATION_RENDER_HVS_PROJECT,
    )
    cap_problems = cap.validate()
    if cap_problems:
        return RenderResult(
            ok=False, state=STATE_RENDER_AUTHORIZATION_REQUIRED,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_CAPABILITY_MALFORMED, error_detail="; ".join(cap_problems), plan=plan,
        )
    store.put_capability(cap)

    re_plan = build_render_plan(
        project_id=project_id, project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id, output_root_identity=output_root_identity,
        now_iso=now_iso,
    )
    if re_plan.plan_hash != plan.plan_hash:
        return RenderResult(
            ok=False, state=STATE_RENDER_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_RENDER_PLAN_MISMATCH,
            error_detail="render plan hash changed between authorization and execution", plan=plan,
        )

    if not store.try_claim_active(project_id=project_id, attempt_id=attempt_id):
        return RenderResult(
            ok=False, state=STATE_RENDER_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_RENDER_ALREADY_ACTIVE,
            error_detail="another render attempt is already active for this project", plan=plan,
        )

    attempt = HvsRenderAttempt(
        attempt_id=attempt_id, project_id=project_id, project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash, render_profile_id=render_profile_id,
        render_plan_hash=plan.plan_hash, authorization_id=authorization.authorization_id,
        capability_id=capability_id, output_root_identity=output_root_identity,
        state=STATE_RENDER_STARTING, hvs_calls=0, render_calls=0,
        created_at=now_iso, updated_at=now_iso, started_at=now_iso,
    )
    store.put_attempt(attempt)

    prior_cap = store.consume_capability(capability_id, consumed_at=now_iso)
    if prior_cap is None:
        attempt = HvsRenderAttempt(
            **{**attempt.to_dict(), "state": STATE_RENDER_FAILED_CONFIRMED,
               "finished_at": now_iso, "updated_at": now_iso, "outcome": "rejected",
               "error_code": ERR_CAPABILITY_CONSUMED,
               "error_detail": "capability already consumed (duplicate request contained)"}
        )
        store.put_attempt(attempt)
        return RenderResult(
            ok=False, state=STATE_RENDER_FAILED_CONFIRMED, attempt_id=attempt_id,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=0, hvs_calls=0, outcome="rejected",
            error_code=ERR_CAPABILITY_CONSUMED,
            error_detail="capability already consumed (duplicate request contained)", plan=plan,
        )

    render_calls = 0
    hvs_calls = 0
    render_result: Optional[dict[str, Any]] = None
    try:
        render_calls = 1
        hvs_calls = 1
        attempt = HvsRenderAttempt(**{**attempt.to_dict(), "state": STATE_RENDER_RUNNING,
                                      "render_calls": render_calls, "hvs_calls": hvs_calls,
                                      "updated_at": now_iso})
        store.put_attempt(attempt)
        if timeout_during_invoke:
            attempt = HvsRenderAttempt(
                **{**attempt.to_dict(), "state": STATE_RENDER_OUTCOME_UNKNOWN,
                   "render_calls": render_calls, "hvs_calls": hvs_calls,
                   "finished_at": now_iso, "updated_at": now_iso, "outcome": "unknown",
                   "error_code": ERR_HVS_RENDER_FAILED,
                   "error_detail": "HVS render did not return (timeout/lost response)"}
            )
            store.put_attempt(attempt)
            return RenderResult(
                ok=False, state=STATE_RENDER_OUTCOME_UNKNOWN, attempt_id=attempt_id,
                authorization_id=authorization.authorization_id, capability_id=capability_id,
                render_calls=render_calls, hvs_calls=hvs_calls, outcome="unknown",
                error_code=ERR_HVS_RENDER_FAILED,
                error_detail="HVS render did not return (timeout/lost response)", plan=plan,
            )
        render_result = hvs_render(
            project_id=normalized_hvs_project_name(project_id), format=render_profile_id,
            request_id=attempt_id, output_root_identity=physical_output_root,
            projects_root=projects_root_identity,
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        attempt = HvsRenderAttempt(
            **{**attempt.to_dict(), "state": STATE_RENDER_OUTCOME_UNKNOWN,
               "render_calls": render_calls, "hvs_calls": hvs_calls,
               "finished_at": now_iso, "updated_at": now_iso, "outcome": "unknown",
               "error_code": ERR_HVS_RENDER_FAILED,
               "error_detail": f"HVS render raised: {type(exc).__name__}"}
        )
        store.put_attempt(attempt)
        return RenderResult(
            ok=False, state=STATE_RENDER_OUTCOME_UNKNOWN, attempt_id=attempt_id,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=render_calls, hvs_calls=hvs_calls, outcome="unknown",
            error_code=ERR_HVS_RENDER_FAILED,
            error_detail=f"HVS render raised: {type(exc).__name__}", plan=plan,
        )

    inspect_result: Optional[dict[str, Any]] = None
    try:
        inspect_result = hvs_inspector(project_id=normalized_hvs_project_name(project_id), request_id=attempt_id)
    except Exception:
        inspect_result = None

    output_relative_path = (render_result or {}).get("output_relative_path") or plan.expected_output_relative_path
    validation = artifact_validator(
        repo_root=None, hvs_repo_root=physical_output_root, project_id=project_id,
        render_request_id=attempt_id, render_approval_id=authorization.authorization_id,
        dispatch_id=attempt_id, hvs_render_id=(render_result or {}).get("render_id"),
        output_relative_path=output_relative_path, selected_format=render_profile_id,
        width=RENDER_PROFILES[render_profile_id].width, height=RENDER_PROFILES[render_profile_id].height,
        fps=RENDER_PROFILES[render_profile_id].fps, target_duration_seconds=0.0,
        video_codec=RENDER_PROFILES[render_profile_id].video_codec,
        pixel_format=RENDER_PROFILES[render_profile_id].pixel_format,
        audio_requirement="NOT_REQUIRED", no_overwrite_policy="FAIL_IF_EXISTS",
        operator_id=operator_id, recorded_at=now_iso,
    )
    verification = (validation or {}).get("verification") or {}
    verified = bool((validation or {}).get("ok")) and bool(verification.get("artifact_verified"))

    artifact_descriptor = None
    if verified:
        probe = verification.get("probe") or {}
        artifact = verification.get("artifact") or {}
        artifact_descriptor = {
            "artifact_id": artifact.get("artifact_id") or attempt_id,
            "render_attempt_id": attempt_id,
            "profile_id": render_profile_id,
            "filename": artifact.get("relative_output_path") or output_relative_path,
            "media_type": "video/mp4",
            "size_bytes": int(artifact.get("size_bytes") or 0),
            "sha256": artifact.get("sha256") or verification.get("sha256") or "",
            "duration": probe.get("video_duration") if probe else None,
            "width": probe.get("width") if probe else None,
            "height": probe.get("height") if probe else None,
            "frame_rate": probe.get("fps") if probe else None,
            "video_codec": probe.get("video_codec") if probe else None,
            "audio_codec": probe.get("audio_codec") if probe else None,
            "validation_state": verification.get("verification_status") or "VERIFIED",
        }

    render_boundary_ok = bool(render_result and render_result.get("ok"))
    if render_boundary_ok:
        discovered = HvsRenderAttempt(
            **{**attempt.to_dict(), "state": STATE_ARTIFACT_DISCOVERED, "render_calls": render_calls,
               "hvs_calls": hvs_calls, "updated_at": now_iso, "outcome": "artifact_discovered"}
        )
        store.put_attempt(discovered)
        attempt = discovered

    if render_boundary_ok and verified:
        validated_attempt = HvsRenderAttempt(
            **{**attempt.to_dict(), "state": STATE_ARTIFACT_VALIDATED, "updated_at": now_iso,
               "outcome": "artifact_validated", "artifact_descriptor": artifact_descriptor}
        )
        store.put_attempt(validated_attempt)
        attempt = validated_attempt

    render_ok = render_boundary_ok and verified
    if render_ok:
        persisted = {
            "project_id": project_id, "hvs_project_name": normalized_hvs_project_name(project_id),
            "output_root_identity": output_root_identity, "attempt_id": attempt_id,
            "authorization_id": authorization.authorization_id, "capability_id": capability_id,
            "render_plan_hash": plan.plan_hash, "render_calls": render_calls,
            "output_relative_path": output_relative_path,
            "artifact_descriptor": artifact_descriptor, "verification": verification,
        }
        attempt = HvsRenderAttempt(
            **{**attempt.to_dict(), "state": STATE_RENDER_SUCCEEDED, "render_calls": render_calls,
               "hvs_calls": hvs_calls, "finished_at": now_iso, "updated_at": now_iso,
               "outcome": "success", "artifact_descriptor": artifact_descriptor,
               "persisted_result": persisted}
        )
        store.put_attempt(attempt)
        return RenderResult(
            ok=True, state=STATE_RENDER_SUCCEEDED, attempt_id=attempt_id,
            authorization_id=authorization.authorization_id, capability_id=capability_id,
            render_calls=render_calls, hvs_calls=hvs_calls, outcome="success",
            persisted_result=persisted, plan=plan, artifact=artifact_descriptor,
        )

    err_code = ERR_ARTIFACT_VALIDATION_FAILED if (render_result and render_result.get("ok")) else ERR_HVS_RENDER_FAILED
    detail = (render_result or {}).get("error_detail") if not verified else "artifact validation failed"
    attempt = HvsRenderAttempt(
        **{**attempt.to_dict(), "state": STATE_RENDER_FAILED_CONFIRMED, "render_calls": render_calls,
           "hvs_calls": hvs_calls, "finished_at": now_iso, "updated_at": now_iso,
           "outcome": "failed", "error_code": err_code,
           "error_detail": str(detail or "HVS render did not confirm an artifact"),
           "artifact_descriptor": None,
           "persisted_result": {"project_id": project_id, "output_root_identity": output_root_identity,
                                "attempt_id": attempt_id, "render_calls": render_calls,
                                "verification": verification}}
    )
    store.put_attempt(attempt)
    return RenderResult(
        ok=False, state=STATE_RENDER_FAILED_CONFIRMED, attempt_id=attempt_id,
        authorization_id=authorization.authorization_id, capability_id=capability_id,
        render_calls=render_calls, hvs_calls=hvs_calls, outcome="failed",
        error_code=err_code, error_detail=str(detail or "HVS render did not confirm an artifact"),
        plan=plan,
    )


# --------------------------------------------------------------------------
# Read-only reconciliation (Cohort 10E §8)
# --------------------------------------------------------------------------

def reconcile_render(
    *,
    store: RenderAttemptStore,
    attempt_id: str,
    hvs_inspector: HvsInspectorCallable,
) -> tuple[str, Optional[HvsRenderAttempt]]:
    """Classify an existing attempt's render output at the output root.

    Read-only: never creates, repairs, overwrites, re-renders, deletes,
    moves, or publishes. Returns (classification, attempt).
    """
    attempt = store.get_attempt(attempt_id)
    if attempt is None:
        return (RECONCILED_ATTEMPT_NOT_FOUND, None)
    if attempt.state not in (
        STATE_RENDER_OUTCOME_UNKNOWN,
        STATE_RENDER_RECONCILIATION_REQUIRED,
        STATE_RENDER_SUCCEEDED,
        STATE_RENDER_FAILED_CONFIRMED,
    ):
        return (ERR_RECONCILE_REQUIRED, attempt)
    try:
        view = hvs_inspector(
            project_id=normalized_hvs_project_name(attempt.project_id),
            request_id=attempt_id,
        )
    except Exception:
        view = None
    if view is None:
        return (RECONCILED_INSPECT_FAILED, attempt)

    # The artifact descriptor (if present) carries the authoritative
    # checksum + size the inspector can confirm on disk.
    artifact = attempt.artifact_descriptor or {}
    expected_sha = artifact.get("sha256") or ""
    expected_size = int(artifact.get("size_bytes") or 0)
    exists = bool(view.get("artifact_exists"))
    sha = view.get("artifact_sha256") or ""
    size = int(view.get("artifact_size_bytes") or 0)

    projected = HvsRenderAttempt(**{**attempt.to_dict(), "reconciliation_count": attempt.reconciliation_count + 1})

    if exists and (sha == expected_sha if expected_sha else sha != "") and (size == expected_size if expected_size else size > 0):
        projected = HvsRenderAttempt(
            **{**projected.to_dict(), "state": STATE_RENDER_SUCCEEDED, "outcome": "success",
               "persisted_result": {**(attempt.persisted_result or {}), "reconciled_projection": True, "inspect": view}}
        )
        return (RECONCILED_SUCCEEDED, projected)

    if exists and sha and expected_sha and sha != expected_sha:
        return (RECONCILED_STILL_UNKNOWN, projected)
    if exists and expected_size and size != expected_size:
        return (RECONCILED_STILL_UNKNOWN, projected)
    if not exists:
        # Only CONFIRMED_NOT (i.e. still unknown) — never auto-fail a render
        # that may have produced output we cannot yet see; but a prior
        # confirmed failure stays failed.
        if attempt.state == STATE_RENDER_FAILED_CONFIRMED:
            return (RECONCILED_FAILED_CONFIRMED, projected)
        return (RECONCILED_STILL_UNKNOWN, projected)
    return (RECONCILED_STILL_UNKNOWN, projected)


__all__ = sorted(
    (
        "RenderResult",
        "normalized_hvs_project_name",
        "build_render_plan",
        "evaluate_readiness",
        "issue_authorization",
        "render",
        "reconcile_render",
        "DEFAULT_TTL_SECONDS",
        "is_safe_output_root",
    )
)
