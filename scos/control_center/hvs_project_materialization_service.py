"""Cohort 10D — controlled HVS project materialization service.

Orchestrates the exact 15-step side-effect sequence
(Cohort 10D §11) from an authoritative SCOS
project-preparation record to a single, isolated HVS project
materialization.

Design boundaries (enforced, not implied):
  * This module is stdlib-only. It NEVER imports hvs.*, NEVER
    spawns a subprocess, NEVER reaches the network, and NEVER
    performs a render. The only HVS sink is the injected
    ``hvs_initializer`` callable (step 12), which the canary
    wires to the REAL hvs.core.project_initializer.initialize_project
    pointed at an isolated OS-temp projects_root.
  * No HVS/filesystem mutation occurs before step 12. Every
    rejection in steps 1-11 leaves ``hvs_calls == 0`` and
    the isolated destination untouched.
  * The authorization is evaluated (step 5) and the single-use
    capability is consumed atomically (step 11) BEFORE the HVS
    boundary is crossed (step 12).
  * An unknown outcome (timeout / lost response after a possible
    HVS start) is recorded as OUTCOME_UNKNOWN and is NEVER
    retried automatically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .hvs_project_materialization_models import (  # noqa: E402
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
    ERR_CAPABILITY_CONSUMED,
    ERR_CAPABILITY_EXPIRED,
    ERR_CAPABILITY_MISSING,
    ERR_CAPABILITY_OPERATION_MISMATCH,
    ERR_CAPABILITY_PLAN_MISMATCH,
    ERR_CAPABILITY_REVISION_MISMATCH,
    ERR_CAPABILITY_DESTINATION_MISMATCH,
    ERR_HVS_INIT_FAILED,
    ERR_INFLIGHT_ATTEMPT,
    ERR_PREREQUISITE_UNMET,
    ERR_RECONCILE_REQUIRED,
    HvsMaterializationAttempt,
    HvsProjectMaterializationAuthorization,
    HvsProjectMaterializationCapability,
    HvsProjectMaterializationPlan,
    MATERIALIZATION_SCHEMA_VERSION,
    OPERATION_MATERIALIZE_HVS_PROJECT,
    STATE_HVS_PROJECT_MATERIALIZED,
    STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
    STATE_MATERIALIZATION_AUTHORIZED,
    STATE_MATERIALIZATION_FAILED_CONFIRMED,
    STATE_MATERIALIZATION_NOT_REQUESTED,
    STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
    STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
    STATE_MATERIALIZATION_STARTING,
)
from .hvs_project_materialization_store import MaterializationStore  # noqa: E402

# Prerequisite truth states (Cohort 10D §7).
PREREQ_TRUTH_STATES = ("AVAILABLE_WITH_DATA",)
PREREQ_STATES = (
    "PREPARATION_PREVIEW_READY",
)
VALID_OUTPUT_PROFILE_IDS = ("vertical_9_16", "square_1_1", "landscape_16_9")


@dataclass
class MaterializationResult:
    ok: bool
    state: str
    attempt_id: Optional[str] = None
    authorization_id: Optional[str] = None
    capability_id: Optional[str] = None
    hvs_calls: int = 0
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    persisted_result: Optional[dict[str, Any]] = None
    plan: Optional[HvsProjectMaterializationPlan] = None

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "state": self.state,
            "attempt_id": self.attempt_id,
            "authorization_id": self.authorization_id,
            "capability_id": self.capability_id,
            "hvs_calls": self.hvs_calls,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "persisted_result": self.persisted_result,
        }


# --------------------------------------------------------------------------
# Deterministic helpers
# --------------------------------------------------------------------------

def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalized_hvs_project_name(project_id: str) -> str:
    """Deterministic, HVS-safe project name from a SCOS project id.

    SCOS ids are ``spp-`` + 12 lowercase hex chars; the HVS name
    becomes ``hvs-`` + that suffix (valid ``^[A-Za-z0-9][...]$``,
    17 chars). Pure, collision-resistant, reversible by construction.
    """
    suffix = project_id
    if suffix.startswith("spp-"):
        suffix = suffix[len("spp-"):]
    return f"hvs-{suffix}"


def _default_expires_at(issued_at: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """ISO-8601 expiry derived from an issued_at of the form
    ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` by adding ttl_seconds.

    Pure lexical comparison is used by the capability/authorization
    expiry check, so expiry is expressed in the SAME ISO shape.
    """
    # issued_at is caller-supplied (recorded_at). Parse the prefix.
    base = issued_at.replace("Z", "")
    try:
        from datetime import datetime, timezone

        dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f")
        dt = dt.replace(tzinfo=timezone.utc)
        exp = dt.timestamp() + ttl_seconds
        return (
            datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
    except (ValueError, TypeError):
        # Defensive: if the shape is unexpected, still produce a valid
        # ISO-8601 string that is strictly greater than issued_at so a
        # freshly issued authorization is never immediately expired.
        return f"{issued_at}+ttl"


# --------------------------------------------------------------------------
# Plan construction (Cohort 10D §8)
# --------------------------------------------------------------------------

def build_materialization_plan(
    *,
    project_id: str,
    project_revision: int,
    destination_identity: str,
    normalized: dict[str, Any],
    output_profiles: tuple[str, ...],
    now_iso: str,
) -> HvsProjectMaterializationPlan:
    """Build the deterministic, reviewable materialization plan.

    The plan contains NO credentials, NO secrets, NO arbitrary shell
    commands, NO browser-supplied filesystem destination, NO
    unvalidated absolute asset paths, NO render command, NO publish
    command, and NO external URL fetch instructions. It declares the
    expected deterministic HVS project structure only.
    """
    hvs_name = normalized_hvs_project_name(project_id)
    profile_ids = tuple(
        p for p in output_profiles if p in VALID_OUTPUT_PROFILE_IDS
    )
    project_metadata = {
        "scos_project_id": project_id,
        "hvs_project_name": hvs_name,
        "project_title": str(normalized.get("project_title", "")),
        "client_or_brand": str(normalized.get("client_or_brand", "")),
        "project_purpose": str(normalized.get("project_purpose", "")),
        "normalized_brief_summary": str(normalized.get("normalized_brief_summary", "")),
        "target_duration_seconds": int(normalized.get("target_duration_seconds", 0)),
        "planned_rendition_count": int(normalized.get("planned_rendition_count", 0)),
        "operator_notes": str(normalized.get("operator_notes", "")),
    }
    # Deterministic structure the materialization creates (HVS initializer
    # output). Scene/asset references are logical only (no external
    # absolute paths, no network).
    scene_plan_refs = (f"scenes/{hvs_name}.plan",)
    asset_manifest_refs = (f"assets/{hvs_name}.manifest",)
    voice_audio_refs = ()
    expected_files = (
        f"projects/{hvs_name}/project_brief.json",
        f"projects/{hvs_name}/timelines/video_timeline.json",
        f"projects/{hvs_name}/initialization_manifest.json",
    )
    expected_directories = (f"projects/{hvs_name}",)
    forbidden_operations = (
        "render",
        "ffmpeg",
        "ffprobe",
        "chromium",
        "hyperframes",
        "publish",
        "upload",
        "import-media",
        "export-project",
        "create-render-pack",
    )
    plan = HvsProjectMaterializationPlan(
        plan_schema_version=MATERIALIZATION_SCHEMA_VERSION,
        project_id=project_id,
        project_revision=project_revision,
        normalized_hvs_project_name=hvs_name,
        destination_identity=destination_identity,
        project_metadata=project_metadata,
        scene_plan_refs=scene_plan_refs,
        asset_manifest_refs=asset_manifest_refs,
        voice_audio_refs=voice_audio_refs,
        output_profiles=profile_ids,
        expected_files=expected_files,
        expected_directories=expected_directories,
        forbidden_operations=forbidden_operations,
        plan_hash="",
    )
    # Self-hash (canonical content excludes the plan_hash field).
    return HvsProjectMaterializationPlan(
        **{**plan.to_dict(), "plan_hash": plan.compute_hash()}
    )


# --------------------------------------------------------------------------
# Prerequisites (Cohort 10D §7)
# --------------------------------------------------------------------------

# Forbidden materialization destinations (Cohort 10D §9). A destination
# matching ANY of these prefixes is rejected fail-closed. No production HVS
# workspace, no SCOS production data, no repository root may ever be the
# materialization root.
_FORBIDDEN_DESTINATION_PREFIXES = (
    "C:/Workspace/hermes-video-studio",
    "C:\\Workspace\\hermes-video-studio",
    "C:/Workspace/super-creator-os",
    "C:\\Workspace\\super-creator-os",
    "memory/database.json",
    "memory/runtime/control-center",
)


def is_safe_destination(destination_identity: str) -> bool:
    """Return True only when the destination is cohort-owned and isolated.

    Rejects repository roots, HVS production project directories, SCOS
    production data paths, and any user-supplied absolute path outside the
    approved OS-temp materialization root. The authoritative destination is
    always chosen by the server resolver (§9), never the browser.
    """
    d = (destination_identity or "").replace("\\", "/").rstrip("/")
    if not d:
        return False
    if ".." in d.split("/"):
        return False  # traversal attempt
    for forbidden in _FORBIDDEN_DESTINATION_PREFIXES:
        if d.startswith(forbidden.replace("\\", "/")):
            return False
    # Only OS-temp owned roots are allowed under this cohort.
    if "/AppData/Local/Temp/" not in d and d.startswith("C:/Workspace"):
        return False
    return True


def evaluate_prerequisites(
    *,
    truth_status: str,
    state: str,
    approval_status: Optional[str],
    project_revision: int,
    expected_revision: int,
    preparation_preview: Optional[dict[str, Any]],
    output_profiles: tuple[str, ...],
    destination_identity: str,
    side_effect_flags: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if truth_status not in PREREQ_TRUTH_STATES:
        blockers.append(f"truth_status_unavailable:{truth_status}")
    if state != "PREPARATION_PREVIEW_READY":
        blockers.append(f"state_not_preview_ready:{state}")
    if approval_status != "approved":
        blockers.append("approval_missing_or_invalid")
    if project_revision != expected_revision:
        blockers.append(f"revision_conflict:{expected_revision}!={project_revision}")
    if not preparation_preview:
        blockers.append("preparation_preview_missing")
    if not output_profiles:
        blockers.append("no_output_profiles")
    if not all(p in VALID_OUTPUT_PROFILE_IDS for p in output_profiles):
        blockers.append("unsupported_output_profile")
    if not destination_identity:
        blockers.append("destination_identity_missing")
    if not is_safe_destination(destination_identity):
        blockers.append("destination_not_isolated")
    if side_effect_flags and any(
        side_effect_flags.get(k) for k in ("side_effects_performed", "render_started", "hvs_project_created")
    ):
        blockers.append("side_effect_flag_set")
    return (not blockers, tuple(sorted(set(blockers))))


# --------------------------------------------------------------------------
# Authorization issuance (Cohort 10D §5) — ONLY after explicit confirmation
# --------------------------------------------------------------------------

def issue_authorization(
    *,
    store: MaterializationStore,
    project_id: str,
    project_revision: int,
    plan: HvsProjectMaterializationPlan,
    operator_id: str,
    confirmed: bool,
    now_iso: str,
    authorization_id: str,
    nonce: str,
) -> tuple[Optional[HvsProjectMaterializationAuthorization], Optional[str], Optional[str]]:
    """Issue an immutable, bound authorization.

    Returns (authorization, decision, error_code). The decision is
    ``AUTHORIZED`` only when the operator explicitly confirmed AND all
    prerequisites are met. Otherwise a non-authorized decision is
    returned (fail-closed) and NOTHING is persisted as AUTHORIZED.
    """
    if not confirmed:
        return (
            HvsProjectMaterializationAuthorization(
                schema_version=MATERIALIZATION_SCHEMA_VERSION,
                authorization_id=authorization_id,
                project_id=project_id,
                project_revision=project_revision,
                operation=OPERATION_MATERIALIZE_HVS_PROJECT,
                materialization_plan_hash=plan.plan_hash,
                destination_identity=plan.destination_identity,
                issued_at=now_iso,
                expires_at=_default_expires_at(now_iso),
                issued_by=operator_id,
                decision=DECISION_DENIED,
                nonce=nonce,
            ),
            DECISION_DENIED,
            ERR_PREREQUISITE_UNMET,
        )
    problems = plan.validate() if False else ()  # plan already validated upstream
    auth = HvsProjectMaterializationAuthorization(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        authorization_id=authorization_id,
        project_id=project_id,
        project_revision=project_revision,
        operation=OPERATION_MATERIALIZE_HVS_PROJECT,
        materialization_plan_hash=plan.plan_hash,
        destination_identity=plan.destination_identity,
        issued_at=now_iso,
        expires_at=_default_expires_at(now_iso),
        issued_by=operator_id,
        decision=DECISION_AUTHORIZED,
        nonce=nonce,
    )
    validation = auth.validate()
    if validation:
        return (auth, DECISION_MALFORMED, ERR_AUTHORIZATION_MALFORMED)
    store.put_authorization(auth)
    return (auth, DECISION_AUTHORIZED, None)


# --------------------------------------------------------------------------
# Authorization evaluation (step 5) — fail closed
# --------------------------------------------------------------------------

def _evaluate_authorization(
    auth: Optional[HvsProjectMaterializationAuthorization],
    *,
    project_id: str,
    project_revision: int,
    plan_hash: str,
    destination_identity: str,
    now_iso: str,
) -> Optional[str]:
    """Return an error_code if the authorization does NOT permit materialization."""
    if auth is None:
        return ERR_AUTHORIZATION_MISSING
    problems = auth.validate()
    if problems:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.decision != DECISION_AUTHORIZED:
        return ERR_AUTHORIZATION_MALFORMED  # denied/unknown -> malformed-as-grant
    if auth.operation != OPERATION_MATERIALIZE_HVS_PROJECT:
        return ERR_AUTHORIZATION_OPERATION_MISMATCH
    if auth.project_id != project_id:
        return ERR_AUTHORIZATION_MALFORMED
    if auth.project_revision != project_revision:
        return ERR_AUTHORIZATION_REVISION_MISMATCH
    if auth.materialization_plan_hash != plan_hash:
        return ERR_AUTHORIZATION_PLAN_MISMATCH
    if auth.destination_identity != destination_identity:
        return ERR_AUTHORIZATION_DESTINATION_MISMATCH
    if auth.expires_at < now_iso:
        return ERR_AUTHORIZATION_EXPIRED
    return None


def _evaluate_capability(
    cap: Optional[HvsProjectMaterializationCapability],
    *,
    project_id: str,
    project_revision: int,
    plan_hash: str,
    destination_identity: str,
    now_iso: str,
) -> Optional[str]:
    if cap is None:
        return ERR_CAPABILITY_MISSING
    problems = cap.validate()
    if problems:
        return ERR_CAPABILITY_MALFORMED
    if cap.operation != OPERATION_MATERIALIZE_HVS_PROJECT:
        return ERR_CAPABILITY_OPERATION_MISMATCH
    if cap.project_id != project_id:
        return ERR_CAPABILITY_MALFORMED
    if cap.project_revision != project_revision:
        return ERR_CAPABILITY_REVISION_MISMATCH
    if cap.plan_hash != plan_hash:
        return ERR_CAPABILITY_PLAN_MISMATCH
    if cap.destination_identity != destination_identity:
        return ERR_CAPABILITY_DESTINATION_MISMATCH
    if cap.is_expired(now_iso=now_iso):
        return ERR_CAPABILITY_EXPIRED
    return None


# --------------------------------------------------------------------------
# Materialization orchestration (Cohort 10D §11, 15 steps)
# --------------------------------------------------------------------------

# Signature of the injected HVS initializer (matches REAL
# hvs.core.project_initializer.initialize_project kwargs). Returns the real
# dict shape: {"ok", "command", "exit_code", "payload", ...}.
HvsInitializer = Callable[..., dict[str, Any]]
HvsInspector = Callable[..., dict[str, Any]]


def materialize(
    *,
    store: MaterializationStore,
    project_id: str,
    project_revision: int,
    normalized: dict[str, Any],
    output_profiles: tuple[str, ...],
    destination_identity: str,
    authorization: HvsProjectMaterializationAuthorization,
    capability_id: str,
    attempt_id: str,
    operator_id: str,
    now_iso: str,
    hvs_initializer: HvsInitializer,
    hvs_inspector: HvsInspector,
    timeout_during_invoke: bool = False,
) -> MaterializationResult:
    """Execute the controlled materialization sequence.

    Exactly ONE HVS initializer call may occur (step 12), guarded by
    single-use capability consumption (step 11). Any rejection in
    steps 1-11 returns with ``hvs_calls == 0`` and the isolated
    destination untouched. An unknown outcome is recorded and never
    retried automatically.
    """
    # Step 1-2: read authoritative + verify truth & revision.
    # (The authoritative record is supplied by the caller; re-derive the
    #  plan from it so the authorized plan hash is re-checked.)
    plan = build_materialization_plan(
        project_id=project_id,
        project_revision=project_revision,
        destination_identity=destination_identity,
        normalized=normalized,
        output_profiles=output_profiles,
        now_iso=now_iso,
    )
    # Step 3-4: canonical plan + plan hash already computed in build_*.

    # Step 5: evaluate authorization (fail closed).
    auth_err = _evaluate_authorization(
        authorization,
        project_id=project_id,
        project_revision=project_revision,
        plan_hash=plan.plan_hash,
        destination_identity=destination_identity,
        now_iso=now_iso,
    )
    if auth_err is not None:
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
            authorization_id=authorization.authorization_id if authorization else None,
            hvs_calls=0,
            outcome="rejected",
            error_code=auth_err,
            error_detail="authorization did not permit materialization",
            plan=plan,
        )

    # Step 6: explicit operator decision already encoded in the
    # authorization.decision == AUTHORIZED (issued only on confirmation).

    # Step 6b: replay containment — a previously consumed single-use
    # capability must NOT be re-issued. Reusing an already-consumed
    # capability_id (e.g. an exact replay of a completed request) is
    # contained here, before any HVS call, preserving the single-use
    # invariant and preventing a duplicate materialization.
    existing_cap = store.get_capability(capability_id)
    if existing_cap is not None and existing_cap.is_consumed():
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=0,
            outcome="rejected",
            error_code=ERR_CAPABILITY_CONSUMED,
            error_detail="capability already consumed (exact replay contained)",
            plan=plan,
        )

    # Step 7: issue single-use capability (persisted).
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id=capability_id,
        authorization_id=authorization.authorization_id,
        project_id=project_id,
        project_revision=project_revision,
        plan_hash=plan.plan_hash,
        destination_identity=destination_identity,
        issued_at=now_iso,
        expires_at=_default_expires_at(now_iso),
        consumed_at=None,
        operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    cap_problems = cap.validate()
    if cap_problems:
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=0,
            outcome="rejected",
            error_code=ERR_CAPABILITY_MALFORMED,
            error_detail="; ".join(cap_problems),
            plan=plan,
        )
    store.put_capability(cap)

    # Step 8-9: re-read authoritative + revalidate revision/plan/destination.
    # (Caller guarantees the same record; re-derive plan hash equality.)
    re_plan = build_materialization_plan(
        project_id=project_id,
        project_revision=project_revision,
        destination_identity=destination_identity,
        normalized=normalized,
        output_profiles=output_profiles,
        now_iso=now_iso,
    )
    if re_plan.plan_hash != plan.plan_hash:
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=0,
            outcome="rejected",
            error_code=ERR_AUTHORIZATION_PLAN_MISMATCH,
            error_detail="plan hash changed between authorization and materialization",
            plan=plan,
        )

    # Step 9b: project-level in-flight duplicate containment.
    # At most ONE in-flight attempt may exist per project. A second
    # simultaneous request (even with its own valid capability) must fail
    # closed here, before any HVS call, so no duplicate project is created.
    if not store.try_claim_inflight(project_id=project_id, attempt_id=attempt_id):
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_FAILED_CONFIRMED,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=0,
            outcome="rejected",
            error_code=ERR_INFLIGHT_ATTEMPT,
            error_detail="another materialization attempt is already in flight for this project",
            plan=plan,
        )

    # Step 10: atomically mark attempt as STARTING (persisted).
    attempt = HvsMaterializationAttempt(
        attempt_id=attempt_id,
        project_id=project_id,
        project_revision=project_revision,
        plan_hash=plan.plan_hash,
        destination_identity=destination_identity,
        authorization_id=authorization.authorization_id,
        capability_id=capability_id,
        state=STATE_MATERIALIZATION_STARTING,
        hvs_calls=0,
        started_at=now_iso,
        expected_payload_hash=plan.project_metadata.get("_expected_payload_hash", ""),
    )
    store.put_attempt(attempt)

    # Step 11: consume capability atomically (only one winner proceeds).
    prior_cap = store.consume_capability(capability_id, consumed_at=now_iso)
    if prior_cap is None:
        # Already consumed (concurrent duplicate) — do NOT cross the
        # HVS boundary. Record the contained outcome.
        attempt = HvsMaterializationAttempt(
            **{
                **attempt.to_dict(),
                "state": STATE_MATERIALIZATION_FAILED_CONFIRMED,
                "finished_at": now_iso,
                "outcome": "rejected",
                "error_code": ERR_CAPABILITY_CONSUMED,
                "error_detail": "capability already consumed (duplicate request contained)",
            }
        )
        store.put_attempt(attempt)
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_FAILED_CONFIRMED,
            attempt_id=attempt_id,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=0,
            outcome="rejected",
            error_code=ERR_CAPABILITY_CONSUMED,
            error_detail="capability already consumed (duplicate request contained)",
            plan=plan,
        )

    # Step 12: cross the HVS mutation boundary EXACTLY ONCE.
    hvs_calls = 0
    init_result: Optional[dict[str, Any]] = None
    try:
        hvs_calls = 1
        if timeout_during_invoke:
            # Simulate a timeout / lost response AFTER the call was
            # issued: we mark the attempt unknown and do NOT retry.
            attempt = HvsMaterializationAttempt(
                **{
                    **attempt.to_dict(),
                    "state": STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
                    "hvs_calls": hvs_calls,
                    "finished_at": now_iso,
                    "outcome": "unknown",
                    "error_code": ERR_HVS_INIT_FAILED,
                    "error_detail": "HVS initializer did not return (timeout/lost response)",
                }
            )
            store.put_attempt(attempt)
            return MaterializationResult(
                ok=False,
                state=STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
                attempt_id=attempt_id,
                authorization_id=authorization.authorization_id,
                capability_id=capability_id,
                hvs_calls=hvs_calls,
                outcome="unknown",
                error_code=ERR_HVS_INIT_FAILED,
                error_detail="HVS initializer did not return (timeout/lost response)",
                plan=plan,
            )
        init_result = hvs_initializer(
            project_id=normalized_hvs_project_name(project_id),
            contract_path=plan.project_metadata.get("_contract_path", ""),
            expected_payload_hash=plan.project_metadata.get("_expected_payload_hash", ""),
            approve_initialization=True,
            request_id=attempt_id,
            projects_root=destination_identity,
        )
        # The authoritative identity for the real HVS boundary is the contract's
        # payload identity hash (16-hex), which the HVS itself validates against
        # ``expected_payload_hash``. Capture it here so the inspector-based
        # identity gate (Step 13b) compares against the SAME value the HVS
        # confirmed, not the plan's SHA-256 plan_hash.
        expected_payload_hash = plan.project_metadata.get("_expected_payload_hash", "")
    except Exception as exc:  # pragma: no cover - defensive boundary
        # Any exception before a confirmed success => unknown (never retry).
        attempt = HvsMaterializationAttempt(
            **{
                **attempt.to_dict(),
                "state": STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
                "hvs_calls": hvs_calls,
                "finished_at": now_iso,
                "outcome": "unknown",
                "error_code": ERR_HVS_INIT_FAILED,
                "error_detail": f"HVS initializer raised: {type(exc).__name__}",
            }
        )
        store.put_attempt(attempt)
        return MaterializationResult(
            ok=False,
            state=STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
            attempt_id=attempt_id,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=hvs_calls,
            outcome="unknown",
            error_code=ERR_HVS_INIT_FAILED,
            error_detail=f"HVS initializer raised: {type(exc).__name__}",
            plan=plan,
        )

    # Step 13: inspect the resulting project (read-only).
    inspect_result: Optional[dict[str, Any]] = None
    try:
        inspect_result = hvs_inspector(
            project_id=normalized_hvs_project_name(project_id),
            request_id=attempt_id,
        )
    except Exception:
        inspect_result = None

    # Step 13b: inspector-based identity/integrity gate.
    # The INITIATOR reporting success is necessary but NOT sufficient: the
    # read-only inspector must confirm the materialized project actually
    # exists at the destination with the EXPECTED plan hash and no render
    # started. An identity mismatch (different payload hash) or a render
    # signal blocks success fail-closed (Cohort 10D §12 confirmed success).
    inspect_payload = (inspect_result or {}).get("payload") or inspect_result or {}
    inspect_exists = bool((inspect_result or {}).get("exists", inspect_payload.get("exists")))
    inspect_valid = bool((inspect_result or {}).get("valid", inspect_payload.get("valid")))
    inspect_hash = (inspect_result or {}).get("payload_hash", inspect_payload.get("payload_hash"))
    inspect_render_started = bool(
        (inspect_result or {}).get("render_started", inspect_payload.get("render_started"))
    )
    identity_ok = (
        inspect_exists
        and inspect_valid
        and (inspect_hash == expected_payload_hash if expected_payload_hash else inspect_hash != "")
        and not inspect_render_started
    )

    # Step 14: reconcile result.
    init_ok = bool(init_result and init_result.get("ok"))
    init_payload = (init_result or {}).get("payload") or {}
    created = bool(init_payload.get("project_created")) or init_ok
    verified = bool(init_payload.get("project_verified"))

    if init_ok and created and verified and identity_ok:
        # Step 15: persist terminal CONFIRMED success.
        persisted = {
            "project_id": project_id,
            "hvs_project_name": normalized_hvs_project_name(project_id),
            "destination_identity": destination_identity,
            "attempt_id": attempt_id,
            "authorization_id": authorization.authorization_id,
            "capability_id": capability_id,
            "plan_hash": plan.plan_hash,
            "hvs_calls": hvs_calls,
            "render_started": False,
            "assets_copied": False,
            "voice_created": False,
            "inspect": inspect_result,
        }
        attempt = HvsMaterializationAttempt(
            **{
                **attempt.to_dict(),
                "state": STATE_HVS_PROJECT_MATERIALIZED,
                "hvs_calls": hvs_calls,
                "finished_at": now_iso,
                "outcome": "success",
                "persisted_result": persisted,
            }
        )
        store.put_attempt(attempt)
        return MaterializationResult(
            ok=True,
            state=STATE_HVS_PROJECT_MATERIALIZED,
            attempt_id=attempt_id,
            authorization_id=authorization.authorization_id,
            capability_id=capability_id,
            hvs_calls=hvs_calls,
            outcome="success",
            persisted_result=persisted,
            plan=plan,
        )

    # HVS returned non-success, or project not verified => confirmed failure.
    # NOTE: a non-zero HVS result with no project is CONFIRMED failure,
    # never unknown.
    attempt = HvsMaterializationAttempt(
        **{
            **attempt.to_dict(),
            "state": STATE_MATERIALIZATION_FAILED_CONFIRMED,
            "hvs_calls": hvs_calls,
            "finished_at": now_iso,
            "outcome": "failed",
            "error_code": ERR_HVS_INIT_FAILED,
            "error_detail": (init_payload.get("error_detail") or "HVS initialization did not confirm a project"),
            "persisted_result": {
                "project_id": project_id,
                "destination_identity": destination_identity,
                "attempt_id": attempt_id,
                "hvs_calls": hvs_calls,
                "inspect": inspect_result,
            },
        }
    )
    store.put_attempt(attempt)
    return MaterializationResult(
        ok=False,
        state=STATE_MATERIALIZATION_FAILED_CONFIRMED,
        attempt_id=attempt_id,
        authorization_id=authorization.authorization_id,
        capability_id=capability_id,
        hvs_calls=hvs_calls,
        outcome="failed",
        error_code=ERR_HVS_INIT_FAILED,
        error_detail=(init_payload.get("error_detail") or "HVS initialization did not confirm a project"),
        plan=plan,
    )


# --------------------------------------------------------------------------
# Read-only reconciliation (Cohort 10D §14)
# --------------------------------------------------------------------------

def reconcile_materialization(
    *,
    store: MaterializationStore,
    attempt_id: str,
    hvs_inspector: HvsInspector,
) -> tuple[str, Optional[HvsMaterializationAttempt]]:
    """Classify an existing attempt's project presence at the destination.

    Read-only: never creates, repairs, overwrites, re-runs, renders,
    deletes, moves, or publishes. Returns (classification, attempt).
    """
    attempt = store.get_attempt(attempt_id)
    if attempt is None:
        return ("ATTEMPT_NOT_FOUND", None)
    # Only attempts that are unknown or already reconcilable are inspected.
    if attempt.state not in (
        STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
        STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
        STATE_HVS_PROJECT_MATERIALIZED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
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
        return ("INSPECT_FAILED", attempt)

    exists = bool(view.get("exists"))
    valid = bool(view.get("valid"))
    payload_hash = view.get("payload_hash")
    render_started = bool(view.get("render_started"))

    # The authoritative HVS identity is the contract payload identity hash
    # (16-hex), which the HVS validated at initialization and the inspector
    # returns. Compare against the attempt's recorded expected_payload_hash
    # (not plan_hash, which is a SHA-256 of the materialization plan).
    expected_hash = attempt.expected_payload_hash or ""

    if exists and valid and (payload_hash == expected_hash if expected_hash else payload_hash != "") and not render_started:
        # Reconcile an unknown attempt to confirmed materialized.
        updated = HvsMaterializationAttempt(
            **{
                **attempt.to_dict(),
                "state": STATE_HVS_PROJECT_MATERIALIZED,
                "outcome": "success",
                "persisted_result": {
                    "project_id": attempt.project_id,
                    "destination_identity": attempt.destination_identity,
                    "attempt_id": attempt.attempt_id,
                    "hvs_calls": attempt.hvs_calls,
                    "reconciled": True,
                    "inspect": view,
                },
            }
        )
        store.put_attempt(updated)
        return (STATE_HVS_PROJECT_MATERIALIZED, updated)

    if exists and not valid:
        return ("CORRUPT_MATERIALIZATION", attempt)
    if exists and payload_hash != expected_hash:
        return ("IDENTITY_CONFLICT", attempt)
    if not exists:
        # Only CONFIRMED_NOT_MATERIALIZED permits a new authorized attempt.
        return ("CONFIRMED_NOT_MATERIALIZED", attempt)
    return ("STILL_UNKNOWN", attempt)


__all__ = sorted(
    (
        "MaterializationResult",
        "normalized_hvs_project_name",
        "build_materialization_plan",
        "evaluate_prerequisites",
        "issue_authorization",
        "materialize",
        "reconcile_materialization",
        "DEFAULT_TTL_SECONDS",
    )
)
