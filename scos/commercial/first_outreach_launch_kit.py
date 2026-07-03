"""SCOS Stage 4.11 first outreach launch kit builder.

Creates deterministic local templates for manual first prospecting preparation.
This module does not send messages, gather leads, or call external services.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

try:
    from .outreach_models import (
        FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION,
        FirstOutreachLaunchKitError,
        FirstOutreachLaunchKitResult,
        OutreachAsset,
        OutreachLaunchProfile,
        OutreachReadinessCheck,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from outreach_models import (
        FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION,
        FirstOutreachLaunchKitError,
        FirstOutreachLaunchKitResult,
        OutreachAsset,
        OutreachLaunchProfile,
        OutreachReadinessCheck,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")
_SENSITIVE_KEY_MARKERS = ("phone", "email", "address", "contact", "email_address", "phone_number")

_MANIFEST = "outreach_readiness_manifest.json"
_LEADS = "lead_list_template.csv"
_MINI_AUDIT = "mini_audit_template.md"
_SCRIPTS = "outreach_scripts.md"
_FOLLOW_UP = "follow_up_sequence.md"
_OFFER = "offer_one_pager.md"
_OBJECTIONS = "objection_handling.md"
_CHECKLIST = "outreach_launch_checklist.md"

_ASSET_SPECS = (
    ("lead_list_template", _LEADS, "csv", "Manual lead tracking template"),
    ("mini_audit_template", _MINI_AUDIT, "markdown", "Manual mini-audit structure"),
    ("outreach_scripts", _SCRIPTS, "markdown", "Manual message scripts"),
    ("follow_up_sequence", _FOLLOW_UP, "markdown", "Manual follow-up timing"),
    ("offer_one_pager", _OFFER, "markdown", "Offer summary for operator review"),
    ("objection_handling", _OBJECTIONS, "markdown", "Manual objection responses"),
    ("outreach_launch_checklist", _CHECKLIST, "markdown", "Readiness checklist"),
)

_LEAD_COLUMNS = (
    "lead_id",
    "business_name",
    "business_type",
    "location",
    "facebook_url",
    "line_or_booking_channel",
    "observed_problem",
    "mini_audit_status",
    "outreach_status",
    "follow_up_date",
    "notes",
)


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, FrozenMap):
        value = value.to_dict()
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _check(
    checks: list[OutreachReadinessCheck],
    check_name: str,
    status: str,
    severity: str,
    *,
    artifact_path: str | None = None,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    checks.append(
        OutreachReadinessCheck.of(
            check_name,
            status,
            severity,
            artifact_path=artifact_path,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=metadata,
        )
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    checks: list[OutreachReadinessCheck],
    metadata: dict[str, Any] | None = None,
) -> FirstOutreachLaunchKitError:
    return FirstOutreachLaunchKitError.of(
        error_kind,
        error_detail,
        failed_step,
        tuple(checks),
        metadata,
    )


def _prepare_kit_dir(
    output_dir: str | Path,
    kit_id: str,
) -> tuple[Path, FirstOutreachLaunchKitError | None]:
    base_dir = Path(str(output_dir))
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        resolved_base = base_dir.resolve(strict=True)
        kit_dir = (resolved_base / kit_id).resolve()
        kit_dir.relative_to(resolved_base)
    except (OSError, ValueError):
        return Path("."), FirstOutreachLaunchKitError.of(
            "VALIDATION_FAILED",
            "kit directory must stay under output_dir",
            "validate_inputs",
            metadata={"output_dir": str(output_dir), "kit_id": kit_id},
        )
    return kit_dir, None


def _read_evidence(path: Path) -> tuple[str, str] | None:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        json.loads(text)
        return ("json", text)
    return ("text", text)


def _inspect_optional_path(
    checks: list[OutreachReadinessCheck],
    label: str,
    value: Any,
) -> dict[str, Any]:
    if value is None or str(value) == "":
        _check(checks, f"inspect_{label}", "skipped", "warning",
               metadata={"provided": False})
        return {"provided": False, "path": None, "kind": None}
    if _is_url(value):
        raise ValueError("URL_EVIDENCE_PATH")
    path = Path(str(value))
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    try:
        kind, text = _read_evidence(path)
    except (OSError, ValueError) as exc:
        raise ValueError(type(exc).__name__) from exc
    _check(checks, f"inspect_{label}", "success", "info",
           artifact_path=str(path), metadata={"provided": True, "kind": kind, "bytes": len(text.encode("utf-8"))})
    return {"provided": True, "path": str(path), "kind": kind}


def _lead_csv() -> str:
    lines: list[str] = []
    class _Sink:
        def write(self, value: str) -> None:
            lines.append(value)
    writer = csv.writer(_Sink(), lineterminator="\n")
    writer.writerow(_LEAD_COLUMNS)
    writer.writerow((
        "synthetic-lead-001",
        "Synthetic Clinic Example",
        "clinic",
        "synthetic local market",
        "synthetic-facebook-page-placeholder",
        "synthetic booking channel placeholder",
        "Booking path and content offer are unclear in public materials.",
        "not_started",
        "not_started",
        "YYYY-MM-DD",
        "Synthetic example row only; replace manually before real use.",
    ))
    return "".join(lines)


def _mini_audit(profile: OutreachLaunchProfile) -> str:
    return (
        "# Mini-Audit Template\n\n"
        "Synthetic/no-real-customer placeholder: replace every example detail manually before real use.\n\n"
        "## Business snapshot\n\n"
        f"- Target market: {profile.target_market}\n"
        f"- Target location: {profile.target_location}\n"
        "- Observed offer: __________\n\n"
        "## What is already working\n\n"
        "- __________\n\n"
        "## Top 3 lost-opportunity observations\n\n"
        "1. __________\n"
        "2. __________\n"
        "3. __________\n\n"
        "## Quick win recommendations\n\n"
        "- __________\n\n"
        "## Suggested next step\n\n"
        "- Ask whether the owner wants a deeper manual audit.\n\n"
        "## Full audit offer handoff\n\n"
        f"- Offer: {profile.primary_offer}\n"
        f"- Starting price: {profile.starting_price}\n"
        f"- Delivery window: {profile.delivery_window}\n"
    )


def _scripts(profile: OutreachLaunchProfile) -> str:
    return (
        "# Manual Outreach Scripts\n\n"
        "These are manual scripts only. Personalize them by hand after reviewing a real business.\n\n"
        "## First message after observation\n\n"
        "Hi, I noticed one small improvement opportunity in your public content and booking path. "
        "Would it be useful if I shared a short manual mini-audit?\n\n"
        "## Follow-up after interest\n\n"
        "Thanks. I will keep it short: I will point out what is working, what may be losing inquiries, "
        "and one or two practical next steps.\n\n"
        "## Full audit offer message\n\n"
        f"If you want the full version, I offer a {profile.primary_offer}. "
        f"The starting price is {profile.starting_price}, with delivery in {profile.delivery_window}.\n\n"
        "## Polite close/no-pressure message\n\n"
        "No pressure at all. If now is not the right time, I can leave the quick notes with you.\n\n"
        "## In-person short pitch\n\n"
        "I help local businesses find simple content and booking improvements before spending more on promotion.\n"
    )


def _follow_up() -> str:
    return (
        "# Manual Follow-Up Sequence\n\n"
        "Manual only. Do not send as a batch.\n\n"
        "## Day 0 initial message\n\n"
        "- Share one specific observation and ask permission to send a mini-audit.\n\n"
        "## Day 1 soft follow-up\n\n"
        "- Ask whether the owner had a chance to review the note.\n\n"
        "## Day 3 value follow-up\n\n"
        "- Share one additional useful observation without pressure.\n\n"
        "## Day 7 close-the-loop message\n\n"
        "- Politely close the loop and invite them to reply later.\n"
    )


def _offer(profile: OutreachLaunchProfile) -> str:
    return (
        "# Offer One-Pager\n\n"
        f"## Offer name\n\n{profile.primary_offer}\n\n"
        f"## Who it is for\n\n{profile.target_market} in {profile.target_location}.\n\n"
        "## Problem it solves\n\n"
        "Unclear content, weak booking paths, and missed inquiry opportunities.\n\n"
        "## What customer receives\n\n"
        "- Short content and booking readiness report\n"
        "- Practical improvement plan\n"
        "- Handoff notes for next steps\n\n"
        f"## Price\n\nStarting price: {profile.starting_price}\n\n"
        f"## Delivery window\n\n{profile.delivery_window}\n\n"
        "## Required customer inputs\n\n"
        "- Public page or content examples\n"
        "- Main offer details\n"
        "- Booking or inquiry path\n\n"
        "## Out-of-scope\n\n"
        "- Ad buying\n"
        "- Account management\n"
        "- Guaranteed sales claims\n\n"
        "## Next step\n\n"
        "- Confirm scope manually and collect complete inputs.\n"
    )


def _objections() -> str:
    return (
        "# Objection Handling Guide\n\n"
        "## Too expensive\n\n"
        "That is fair. Start only if the audit would help you make clearer content or booking decisions.\n\n"
        "## We already have staff\n\n"
        "Great. This can give your team an outside checklist to compare against their current plan.\n\n"
        "## We do not need AI\n\n"
        "Understood. The useful part is the practical audit and checklist, not a technology label.\n\n"
        "## Can you guarantee sales\n\n"
        "No. I can identify improvement opportunities, but results depend on the offer, market, and execution.\n\n"
        "## Send me details\n\n"
        "I can share a short one-page summary of scope, price, inputs, and delivery window.\n\n"
        "## Not ready now\n\n"
        "No problem. Keep the quick notes and revisit when timing is better.\n"
    )


def _checklist() -> str:
    return (
        "# Outreach Launch Checklist\n\n"
        "- [ ] Sample report ready\n"
        "- [ ] Offer price ready\n"
        "- [ ] Lead list ready\n"
        "- [ ] Mini audit template ready\n"
        "- [ ] Manual outreach script ready\n"
        "- [ ] Follow-up sequence ready\n"
        "- [ ] Delivery workflow ready\n"
        "- [ ] Acceptance/checklist workflow ready\n"
        "- [ ] No real PII stored in templates\n"
        "- [ ] No automated sending enabled\n"
    )


def _asset_records(kit_dir: Path) -> tuple[OutreachAsset, ...]:
    return tuple(
        OutreachAsset.of(
            asset_name,
            file_name,
            asset_type,
            purpose,
            required=True,
            path=str(kit_dir / file_name),
        )
        for asset_name, file_name, asset_type, purpose in _ASSET_SPECS
    )


def _manifest_payload(
    result: FirstOutreachLaunchKitResult,
    evidence_inputs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    data = result.to_dict()
    data["evidence_inputs"] = list(evidence_inputs)
    return data


def create_first_outreach_launch_kit(
    *,
    output_dir: str | Path,
    created_at: str,
    profile: OutreachLaunchProfile | None = None,
    kit_id: str | None = None,
    launch_certification_pack_path: str | Path | None = None,
    operator_practice_report_path: str | Path | None = None,
    overwrite: bool = False,
) -> FirstOutreachLaunchKitResult | FirstOutreachLaunchKitError:
    checks: list[OutreachReadinessCheck] = []

    if output_dir is None or str(output_dir) == "":
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", checks)
    if not isinstance(created_at, str) or not created_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="created_at is required")
        return _error("INVALID_ARGUMENTS", "created_at is required", "validate_inputs", checks)
    for label, value in (
        ("output_dir", output_dir),
        ("launch_certification_pack_path", launch_certification_pack_path),
        ("operator_practice_report_path", operator_practice_report_path),
    ):
        if _is_url(value):
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="paths must be local filesystem paths",
                   metadata={"argument": label, "path": str(value)})
            return _error("INVALID_ARGUMENTS", "paths must be local filesystem paths",
                          "validate_inputs", checks, {"argument": label, "path": str(value)})

    resolved_profile = profile if profile is not None else OutreachLaunchProfile.default()
    if not isinstance(resolved_profile, OutreachLaunchProfile):
        _check(checks, "prepare_profile", "failure", "error",
               error_kind="INVALID_PROFILE", error_detail="profile must be an OutreachLaunchProfile")
        return _error("INVALID_PROFILE", "profile must be an OutreachLaunchProfile", "prepare_profile", checks)
    if _contains_sensitive_key(resolved_profile.metadata):
        _check(checks, "prepare_profile", "failure", "error",
               error_kind="INVALID_PROFILE", error_detail="profile metadata contains sensitive contact-like keys")
        return _error("INVALID_PROFILE", "profile metadata contains sensitive contact-like keys",
                      "prepare_profile", checks)
    _check(checks, "prepare_profile", "success", "info", metadata={"profile_id": resolved_profile.profile_id})

    resolved_kit_id = str(kit_id) if kit_id is not None else f"first-outreach-launch-kit-{resolved_profile.profile_id}"
    kit_dir, dir_error = _prepare_kit_dir(output_dir, resolved_kit_id)
    if dir_error is not None:
        return dir_error
    if kit_dir.exists() and not overwrite:
        _check(checks, "validate_inputs", "failure", "error", artifact_path=str(kit_dir),
               error_kind="OUTPUT_ALREADY_EXISTS", error_detail="kit directory already exists and overwrite is False")
        return _error("OUTPUT_ALREADY_EXISTS", "kit directory already exists and overwrite is False",
                      "validate_inputs", checks, {"path": str(kit_dir)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(kit_dir))

    evidence_inputs: list[dict[str, Any]] = []
    try:
        evidence_inputs.append(_inspect_optional_path(checks, "launch_certification_pack", launch_certification_pack_path))
        evidence_inputs.append(_inspect_optional_path(checks, "operator_practice_report", operator_practice_report_path))
    except FileNotFoundError as exc:
        _check(checks, "inspect_optional_evidence", "failure", "error",
               error_kind="INPUT_NOT_FOUND", error_detail="optional evidence path does not exist",
               metadata={"path": str(exc)})
        return _error("INPUT_NOT_FOUND", "optional evidence path does not exist",
                      "inspect_optional_evidence", checks, {"path": str(exc)})
    except ValueError as exc:
        kind = "INVALID_ARGUMENTS" if str(exc) == "URL_EVIDENCE_PATH" else "INVALID_EVIDENCE"
        detail = "optional evidence path must be local" if kind == "INVALID_ARGUMENTS" else "optional evidence is not readable"
        _check(checks, "inspect_optional_evidence", "failure", "error",
               error_kind=kind, error_detail=detail)
        return _error(kind, detail, "inspect_optional_evidence", checks)

    try:
        kit_dir.mkdir(parents=True, exist_ok=True)
        files = {
            _LEADS: _lead_csv(),
            _MINI_AUDIT: _mini_audit(resolved_profile),
            _SCRIPTS: _scripts(resolved_profile),
            _FOLLOW_UP: _follow_up(),
            _OFFER: _offer(resolved_profile),
            _OBJECTIONS: _objections(),
            _CHECKLIST: _checklist(),
        }
        for file_name, text in files.items():
            path = kit_dir / file_name
            path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")
            _check(checks, f"write_{Path(file_name).stem}", "success", "info", artifact_path=str(path))
    except OSError as exc:
        _check(checks, "write_templates", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="outreach kit files could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "outreach kit files could not be written",
                      "write_templates", checks, {"os_error": type(exc).__name__})

    assets = _asset_records(kit_dir)
    missing_assets = [asset.file_name for asset in assets if not Path(str(asset.path)).is_file()]
    if missing_assets:
        _check(checks, "summarize_go_no_go", "failure", "error",
               error_kind="VALIDATION_FAILED", error_detail="required outreach assets are missing",
               metadata={"missing_assets": missing_assets})
        ready = False
        go_no_go = "NO_GO"
    else:
        _check(checks, "summarize_go_no_go", "success", "info",
               metadata={"required_asset_count": len(assets)})
        ready = True
        go_no_go = "GO" if all(item.get("provided") for item in evidence_inputs) else "CONDITIONAL_GO"

    manifest_path = kit_dir / _MANIFEST
    result = FirstOutreachLaunchKitResult(
        ok=True,
        schema_version=FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION,
        kit_id=resolved_kit_id,
        profile=resolved_profile,
        created_at=created_at,
        output_dir=str(kit_dir),
        manifest_path=str(manifest_path),
        assets=assets,
        checks=tuple(checks),
        ready_for_outreach=ready,
        go_no_go=go_no_go,
        metadata=FrozenMap.from_mapping(
            {
                "builder": "scos.commercial.first_outreach_launch_kit",
                "manual_only": True,
                "optional_evidence_count": sum(1 for item in evidence_inputs if item.get("provided")),
            }
        ),
    )
    try:
        manifest_path.write_text(_json_text(_manifest_payload(result, tuple(evidence_inputs))),
                                 encoding="utf-8", newline="\n")
    except OSError as exc:
        _check(checks, "write_manifest", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="outreach readiness manifest could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "outreach readiness manifest could not be written",
                      "write_manifest", checks, {"os_error": type(exc).__name__})
    return result


__all__ = ("create_first_outreach_launch_kit",)
