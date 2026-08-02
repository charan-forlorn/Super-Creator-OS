"""Authoritative paid-pilot packet-admission boundary (§6.A).

This is the SINGLE versioned authority that admits a pilot authorization packet.
It is read-only on the packet and produces one durable admission record + audit
event. It is NOT the post-render delivery-readiness authority
(``hvs_paid_pilot_readiness``) and never reuses or renames that module.

Server-control principle:
  * The packet path is resolved server-side from a TRUSTED server variable
    (``SCOS_PILOT_PACKET_PATH``) or an explicit server-supplied path validated
    against an allowed intake root. The browser never submits an arbitrary
    local path.
  * ``expected_sha256`` is supplied by the operator seal (trusted) and verified.
  * Asset bytes are re-validated against declared hashes/sizes. Path traversal
    and reparse-point escapes are rejected.
  * Identity evidence is verified by SHA-256 against the declared reference.

Browser-safe output: the admission projection contains NO absolute paths, no raw
evidence bytes, no PII beyond the already-public pilot/customer/project refs, and
no secret material.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "scos-hvs.pilot-packet-admission.v1/1.0.0"
GATE_TOKENS = (
    "PACKET_VALID",
    "ASSET_COUNT",
    "ASSET_INTEGRITY",
    "IDENTITY_EVIDENCE",
    "RIGHTS",
    "PRIVACY",
    "DELIVERY_SCOPE",
    "RETENTION",
    "EXTERNAL_ACTION_RESTRICTIONS",
)
REQUIRED_TOP_FIELDS = (
    "schema_version", "packet_type", "pilot_id", "customer_ref", "project_ref",
    "customer_identity_evidence_reference", "customer_identity_evidence_sha256",
    "operator_approval_timestamp", "approved_customer_assets", "content_rights_declaration",
    "privacy", "external_action_restrictions", "required_packet_decisions",
)
ALLOWED_ASSET_SUFFIX = {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".wav", ".mp4", ".mov", ".pdf", ".txt"}
PROHIBITED_PRIVACY_VALUES = {"yes", "true", "1"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_link_or_reparse(p: Path) -> bool:
    parts = Path(p).resolve().parts
    for i in range(1, len(parts) + 1):
        q = Path(*parts[:i])
        try:
            if q.exists() and q.is_symlink():
                return True
        except OSError:
            return True
        try:
            if os.name == "nt" and q.exists():
                import stat

                if q.stat().st_file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    return True
        except OSError:
            return True
    return False


def _inside_git(p: Path) -> bool:
    p = Path(p).resolve()
    return any((q / ".git").exists() for q in (p, *p.parents))


def _is_within(base: Path, child: Path) -> bool:
    try:
        Path(child).resolve().relative_to(Path(base).resolve())
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class AdmissionGate:
    token: str
    passed: bool
    reason_code: str
    detail: str


@dataclass(frozen=True)
class AssetIntegrity:
    asset_id: str
    safe_name: str
    declared_sha256: str
    actual_sha256: str
    declared_size: int
    actual_size: int
    status: str  # OK | HASH_MISMATCH | SIZE_MISMATCH | NOT_FOUND | PATH_ESCAPE | UNSUPPORTED_TYPE
    purpose: str
    rights_declaration: str
    privacy_classification: str


@dataclass(frozen=True)
class AdmissionResult:
    ok: bool
    error_code: Optional[str]
    detail: Optional[str]
    gates: tuple[AdmissionGate, ...] = ()
    assets: tuple[AssetIntegrity, ...] = ()
    projection: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_code": self.error_code,
            "detail": self.detail,
            "gates": [g.__dict__ for g in self.gates],
            "assets": [a.__dict__ for a in self.assets],
            "projection": self.projection,
        }


def _find_packet_path(*, explicit_path: Optional[str], allowed_root: Path, environ: dict[str, str]) -> Path:
    """Resolve a trusted packet path. Browser never supplies this."""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if not _is_within(allowed_root, p):
            raise ValueError("PACKET_PATH_ESCAPE")
        return p
    env_path = environ.get("SCOS_PILOT_PACKET_PATH")
    if not env_path:
        raise ValueError("PACKET_PATH_NOT_CONFIGURED")
    return Path(env_path).resolve()


def _verify_assets(packet: dict[str, Any], approved_input_root: Path) -> list[AssetIntegrity]:
    out: list[AssetIntegrity] = []
    for a in packet.get("approved_customer_assets", []) or []:
        aid = str(a.get("asset_id", ""))
        safe = str(a.get("safe_name", ""))
        decl_sha = str(a.get("sha256", "")).lower()
        decl_size = int(a.get("size_bytes", 0) or 0)
        rel = a.get("source_location_reference", safe)
        candidate = (approved_input_root / rel)
        status = "OK"
        actual_sha = ""
        actual_size = 0
        try:
            candidate = candidate.resolve()
            if not _is_within(approved_input_root, candidate) or _has_link_or_reparse(candidate):
                status = "PATH_ESCAPE"
            elif not candidate.is_file():
                status = "NOT_FOUND"
            else:
                suffix = Path(safe).suffix.lower()
                if suffix not in ALLOWED_ASSET_SUFFIX:
                    status = "UNSUPPORTED_TYPE"
                else:
                    actual_sha = _sha256_file(candidate)
                    actual_size = candidate.stat().st_size
                    if actual_sha.lower() != decl_sha:
                        status = "HASH_MISMATCH"
                    elif actual_size != decl_size:
                        status = "SIZE_MISMATCH"
        except Exception:
            status = "NOT_FOUND"
        out.append(AssetIntegrity(
            asset_id=aid, safe_name=safe, declared_sha256=decl_sha, actual_sha256=actual_sha,
            declared_size=decl_size, actual_size=actual_size, status=status,
            purpose=str(a.get("declared_purpose", "")), rights_declaration=str(a.get("rights_declaration", "")),
            privacy_classification=str(a.get("privacy_classification", "")),
        ))
    return out


def _verify_identity_evidence(packet: dict[str, Any], approved_input_root: Path) -> tuple[bool, str]:
    ref = packet.get("customer_identity_evidence_reference", "")
    decl = str(packet.get("customer_identity_evidence_sha256", "")).lower()
    if not ref or not decl:
        return (False, "IDENTITY_EVIDENCE_MISSING")
    try:
        p = (approved_input_root / ref).resolve()
        if not _is_within(approved_input_root, p) or not p.is_file():
            return (False, "IDENTITY_EVIDENCE_NOT_FOUND")
        actual = _sha256_file(p)
        if actual.lower() != decl:
            return (False, "IDENTITY_EVIDENCE_HASH_MISMATCH")
        return (True, "OK")
    except Exception:
        return (False, "IDENTITY_EVIDENCE_UNREADABLE")


def admit_packet(
    *,
    packet_path: Optional[str] = None,
    approved_input_root: str,
    admission_store_path: str,
    audit_store_path: str,
    expected_sha256: str,
    environ: Optional[dict[str, str]] = None,
) -> AdmissionResult:
    """Authoritative packet admission. Fails closed on any gate failure."""
    env = environ if environ is not None else dict(os.environ)
    gates: list[AdmissionGate] = []
    try:
        root = Path(approved_input_root).resolve()
        if not root.is_dir():
            return AdmissionResult(False, "INPUT_ROOT_INVALID", f"approved input root missing: {approved_input_root}")
        pp = _find_packet_path(explicit_path=packet_path, allowed_root=root, environ=env)
    except ValueError as e:
        return AdmissionResult(False, str(e), "packet path not trusted or escaped allowed root")

    # Read + SHA verification (gate: PACKET_VALID)
    try:
        raw = pp.read_bytes()
    except Exception:
        return AdmissionResult(False, "PACKET_UNREADABLE", "packet could not be read")
    actual_sha = _sha256_bytes(raw)
    if expected_sha256 and actual_sha.lower() != expected_sha256.lower():
        gates.append(AdmissionGate("PACKET_VALID", False, "PACKET_SHA256_MISMATCH",
                                   f"expected {expected_sha256}; got {actual_sha}"))
        return AdmissionResult(False, "PACKET_SHA256_MISMATCH",
                               "packet SHA-256 did not match the operator seal", gates=tuple(gates))
    try:
        packet = json.loads(raw.decode("utf-8"))
    except Exception:
        gates.append(AdmissionGate("PACKET_VALID", False, "PACKET_JSON_INVALID", "packet is not valid JSON"))
        return AdmissionResult(False, "PACKET_JSON_INVALID", "packet is not valid UTF-8 JSON", gates=tuple(gates))
    gates.append(AdmissionGate("PACKET_VALID", True, "OK", "packet read and hash verified"))

    # Structural validation
    missing = [f for f in REQUIRED_TOP_FIELDS if f not in packet]
    if missing:
        gates.append(AdmissionGate("PACKET_VALID", False, "PACKET_MISSING_FIELDS", f"missing: {','.join(missing)}"))
        return AdmissionResult(False, "PACKET_STRUCTURE_INVALID", f"missing fields: {missing}", gates=tuple(gates))

    # Timestamp validation
    ts = packet.get("operator_approval_timestamp", "")
    if not ts or not isinstance(ts, str) or "T" not in ts:
        gates.append(AdmissionGate("PACKET_VALID", False, "APPROVAL_TIMESTAMP_INVALID", "operator approval timestamp missing/invalid"))
        return AdmissionResult(False, "APPROVAL_TIMESTAMP_INVALID", "approval timestamp invalid", gates=tuple(gates))

    # Identity reconciliation (gate: IDENTITY_EVIDENCE)
    ok_id, id_reason = _verify_identity_evidence(packet, root)
    gates.append(AdmissionGate("IDENTITY_EVIDENCE", ok_id, id_reason,
                               "identity evidence verified" if ok_id else id_reason))
    if not ok_id:
        return AdmissionResult(False, "IDENTITY_EVIDENCE_FAILED", id_reason, gates=tuple(gates))

    # Asset integrity (gates: ASSET_COUNT, ASSET_INTEGRITY)
    assets = _verify_assets(packet, root)
    expected_count = len(packet.get("approved_customer_assets", []) or [])
    count_ok = len(assets) == expected_count and expected_count > 0
    gates.append(AdmissionGate("ASSET_COUNT", count_ok, "OK" if count_ok else "ASSET_COUNT_MISMATCH",
                               f"declared {expected_count}; verified {len(assets)}"))
    all_ok = all(a.status == "OK" for a in assets)
    gates.append(AdmissionGate("ASSET_INTEGRITY", all_ok, "OK" if all_ok else "ASSET_INTEGRITY_FAILED",
                               "all assets hash/size verified" if all_ok else "one or more assets failed verification"))
    if not count_ok or not all_ok:
        reasons = [f"{a.safe_name}:{a.status}" for a in assets if a.status != "OK"]
        return AdmissionResult(False, "ASSET_VERIFICATION_FAILED", "; ".join(reasons), gates=tuple(gates), assets=tuple(assets))

    # Rights / privacy / decisions (gates: RIGHTS, PRIVACY)
    crd = packet.get("content_rights_declaration", {}) or {}
    def _norm(v: str) -> str:
        return str(v).strip().lower().replace("-", "_").replace(" ", "_")
    _RIGHTS_OK = {"owned", "licensed", "not_used", "open_source_approved"}
    rights_ok = all(
        _norm(crd.get(k)) in _RIGHTS_OK
        for k in ("asset_owner", "music_used", "font_policy")
    ) and _norm(crd.get("identifiable_person")) in ("no", "yes")
    gates.append(AdmissionGate("RIGHTS", rights_ok, "OK" if rights_ok else "RIGHTS_INCOMPLETE",
                               "content rights declared" if rights_ok else "content rights incomplete"))
    priv = packet.get("privacy", {}) or {}
    priv_ok = not any(str(priv.get(k, "")).strip().lower() in PROHIBITED_PRIVACY_VALUES
                      for k in ("health_data", "financial_data", "government_identifiers", "child_information"))
    gates.append(AdmissionGate("PRIVACY", priv_ok, "OK" if priv_ok else "PRIVACY_PROHIBITED",
                               "privacy classification safe" if priv_ok else "prohibited privacy data declared"))
    if not (rights_ok and priv_ok):
        return AdmissionResult(False, "RIGHTS_PRIVACY_REJECTED", "rights/privacy gate failed", gates=tuple(gates))

    # Delivery scope (gate: DELIVERY_SCOPE)
    dm = packet.get("delivery_method", "")
    delivery_ok = dm in ("MANUAL_OPERATOR_HANDOFF_ONLY", "manual operator handoff")
    gates.append(AdmissionGate("DELIVERY_SCOPE", delivery_ok, "OK" if delivery_ok else "DELIVERY_SCOPE_UNSAFE",
                               "manual operator handoff only" if delivery_ok else "unsafe delivery method"))

    # Retention (gate: RETENTION)
    ret_ok = bool(packet.get("retention_requirement") or packet.get("retention_policy"))
    gates.append(AdmissionGate("RETENTION", ret_ok, "OK" if ret_ok else "RETENTION_UNDEFINED",
                               "retention defined" if ret_ok else "retention requirement missing"))

    # External action restrictions (gate: EXTERNAL_ACTION_RESTRICTIONS)
    ear = packet.get("external_action_restrictions", {}) or {}
    ext_ok = all(str(ear.get(k, "")).upper() == "NOT_AUTHORIZED" for k in
                 ("publishing", "upload", "external_delivery", "customer_notification", "deployment"))
    gates.append(AdmissionGate("EXTERNAL_ACTION_RESTRICTIONS", ext_ok, "OK" if ext_ok else "EXTERNAL_ACTION_NOT_LOCKED",
                               "all external actions NOT_AUTHORIZED" if ext_ok else "external action not locked down"))

    if not (delivery_ok and ret_ok and ext_ok):
        return AdmissionResult(False, "SCOPE_OR_RESTRICTION_REJECTED",
                               "delivery/retention/external-restriction gate failed", gates=tuple(gates))

    # Decision consistency
    dec = packet.get("required_packet_decisions", {}) or {}
    if not bool(dec.get("CUSTOMER_DATA_AUTHORIZED")) or bool(dec.get("PUBLISHING_AUTHORIZED")):
        return AdmissionResult(False, "DECISION_INCONSISTENT",
                               "required decisions inconsistent", gates=tuple(gates))

    # Persist admission record + audit event (durable, fail-closed write).
    projection = _browser_safe_projection(packet, assets, actual_sha)
    record = {
        "schema_version": SCHEMA_VERSION,
        "admitted_at": _now_iso(),
        "packet_sha256": actual_sha,
        "pilot_id": packet.get("pilot_id"),
        "customer_ref": packet.get("customer_ref"),
        "project_ref": packet.get("project_ref"),
        "asset_count": len(assets),
        "asset_safe_names": [a.safe_name for a in assets],
        "gates": [g.__dict__ for g in gates],
        "projection": projection,
    }
    try:
        _atomic_write_json(Path(admission_store_path), record)
        _append_audit(Path(audit_store_path), {
            "schema_version": SCHEMA_VERSION, "event_type": "PACKET_ADMITTED",
            "packet_sha256": actual_sha, "pilot_id": packet.get("pilot_id"),
            "project_ref": packet.get("project_ref"), "asset_count": len(assets),
        })
    except Exception as e:
        return AdmissionResult(False, "ADMISSION_PERSIST_FAILED", f"could not persist admission: {e}",
                               gates=tuple(gates), assets=tuple(assets))

    return AdmissionResult(True, None, None, gates=tuple(gates), assets=tuple(assets), projection=projection)


def _browser_safe_projection(packet: dict[str, Any], assets: list[AssetIntegrity], packet_sha256: str) -> dict[str, Any]:
    """No absolute paths, no raw evidence, no PII beyond public refs."""
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_sha256": packet_sha256[:16] + "...",  # truncated fingerprint only
        "pilot_id": packet.get("pilot_id"),
        "customer_ref": packet.get("customer_ref"),
        "project_ref": packet.get("project_ref"),
        "output_profile": packet.get("target_output_profile") or packet.get("project_identity", {}).get("output_profile"),
        "duration": packet.get("project_identity", {}).get("duration"),
        "title": packet.get("project_identity", {}).get("project_title"),
        "asset_count": len(assets),
        "assets": [
            {"asset_id": a.asset_id, "safe_name": a.safe_name, "status": a.status,
             "purpose": a.purpose, "rights_declaration": a.rights_declaration,
             "privacy_classification": a.privacy_classification}
            for a in assets
        ],
        "external_action_restrictions": packet.get("external_action_restrictions"),
        "delivery_method": packet.get("delivery_method"),
        "font_policy": (packet.get("content_rights_declaration", {}) or {}).get("font_policy"),
    }


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    Path(tmp).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _append_audit(path: Path, event: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
