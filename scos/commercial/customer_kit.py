"""SCOS Stage 4.6 first customer operating kit generator.

Converts an *accepted* Stage 4.5 commercial acceptance result into a
deterministic local folder that an operator can use to serve the first real
customer. This is an operating-kit layer only: it inspects artifacts that
already exist on the local filesystem, generates customer-facing and
operator-facing markdown plus a kit manifest, optionally copies evidence, and
never rebuilds reports, never rebuilds packages, never re-runs any Stage 4 flow,
and never touches the Stage 3 knowledge layer. Inspected artifacts are read but
never mutated or deleted.

Input adaptation: the real Stage 4.5 acceptance artifact
(``commercial_acceptance_report.json``) records ``certification_id``,
``overall_status`` and ``created_at``; this generator maps those to
``acceptance_id``, an ``accepted`` boolean (``ok`` and ``overall_status`` PASS)
and ``checked_at``. The source artifact paths (run manifest, report, package,
package manifest) are read from the Stage 4.4 run manifest, discovered from the
acceptance report's ``evidence_paths`` when ``run_manifest_path`` is not given.

Determinism: ``created_at`` is an explicit injected string (no real clock, no
random, no UUID). The kit id derives from ``customer_id`` when not provided.
All JSON is written UTF-8 with LF newlines using
``json.dumps(..., sort_keys=True, indent=2)``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .customer_kit_models import (
        CUSTOMER_KIT_SCHEMA_VERSION,
        CustomerKitError,
        CustomerKitFile,
        CustomerKitResult,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from customer_kit_models import (
        CUSTOMER_KIT_SCHEMA_VERSION,
        CustomerKitError,
        CustomerKitFile,
        CustomerKitResult,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")

_RUN_MANIFEST_FILENAME = "commercial_run_manifest.json"
_KIT_MANIFEST_FILENAME = "customer_kit_manifest.json"

_REQUIRED_ACCEPTANCE_KEYS = (
    "ok",
    "schema_version",
    "certification_id",
    "run_id",
    "delivery_id",
    "created_at",
    "overall_status",
    "checks",
    "evidence_paths",
)

# Stage 4 delivery-package files an operator sends to the customer.
_DELIVERY_PACKAGE_FILES = (
    "report.md",
    "report.json",
    "qa_summary.md",
    "improvement_plan.md",
    "manifest.json",
)


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _fs_safe(name: str) -> str:
    """Deterministic, Windows-safe folder name for a kit id."""

    return name.replace(":", "_")


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _existing_file(value: Any) -> bool:
    if value is None or _is_url(value):
        return False
    path = Path(str(value))
    return path.exists() and path.is_file()


def _existing_dir(value: Any) -> bool:
    if value is None or _is_url(value):
        return False
    path = Path(str(value))
    return path.exists() and path.is_dir()


# --------------------------------------------------------------------------- #
# Deterministic static markdown templates
# --------------------------------------------------------------------------- #
def _md_intake(customer_id: str, customer_name: str, offer_name: str) -> str:
    return (
        "# Customer Intake Checklist\n\n"
        f"- Customer id: `{customer_id}`\n"
        f"- Customer name: {customer_name}\n"
        f"- Offer: {offer_name}\n\n"
        "## Customer identity\n"
        "- [ ] Customer name confirmed\n"
        "- [ ] Primary contact confirmed\n"
        "- [ ] Billing contact confirmed\n\n"
        "## Business goal\n"
        "- [ ] Primary goal for this delivery captured\n"
        "- [ ] Success metric agreed\n\n"
        "## Source materials received\n"
        "- [ ] Source video / content received\n"
        "- [ ] Brand or style references received\n"
        "- [ ] Required access / rights confirmed\n\n"
        "## Video/content input readiness\n"
        "- [ ] Source is playable and complete\n"
        "- [ ] Duration / resolution acceptable\n\n"
        "## Delivery expectation\n"
        "- [ ] Delivery format agreed\n"
        "- [ ] Delivery date agreed\n\n"
        "## Approval status\n"
        "- [ ] Scope approved\n"
        "- [ ] Ready to start\n"
    )


def _md_sop(customer_id: str) -> str:
    return (
        "# Operator SOP\n\n"
        f"Operating procedure for customer `{customer_id}`.\n\n"
        "## Pre-run checks\n"
        "- [ ] Intake checklist complete\n"
        "- [ ] Source materials staged locally\n\n"
        "## Run commercial delivery\n"
        "- [ ] Execute the Stage 4.4 local commercial run\n"
        "- [ ] Confirm run manifest written\n\n"
        "## Run acceptance gate\n"
        "- [ ] Execute the Stage 4.5 acceptance gate\n"
        "- [ ] Confirm acceptance status is PASS\n\n"
        "## Generate customer kit\n"
        "- [ ] Execute the Stage 4.6 kit generator against the accepted report\n"
        "- [ ] Confirm kit manifest written\n\n"
        "## Manual review\n"
        "- [ ] Review generated report and QA summary\n"
        "- [ ] Review files-to-send list\n\n"
        "## Handoff\n"
        "- [ ] Send delivery package files to customer\n"
        "- [ ] Record handoff in follow-up checklist\n"
    )


def _md_handoff(customer_id: str, customer_name: str) -> str:
    return (
        "# Delivery Handoff\n\n"
        f"Prepared for {customer_name} (`{customer_id}`).\n\n"
        "## What is included\n"
        "- Commercial report (`report.md`, `report.json`)\n"
        "- QA summary (`qa_summary.md`)\n"
        "- Improvement plan (`improvement_plan.md`)\n"
        "- Package manifest (`manifest.json`)\n\n"
        "## How to review files\n"
        "- Open `report.md` for the summary\n"
        "- Open `qa_summary.md` for quality notes\n"
        "- Open `improvement_plan.md` for recommended next steps\n\n"
        "## What to approve\n"
        "- [ ] Confirm the delivered output matches the agreed scope\n"
        "- [ ] Note any requested revisions\n\n"
        "## Next step\n"
        "- Reply with approval or revision notes to proceed.\n"
    )


def _md_certificate(
    acceptance_id: str,
    run_id: str,
    delivery_id: str,
    checked_at: str,
    overall_status: str,
    checks: list[dict[str, Any]],
) -> str:
    lines = [
        "# Acceptance Certificate\n",
        f"- Acceptance id: `{acceptance_id}`",
        f"- Run id: `{run_id}`",
        f"- Delivery id: `{delivery_id}`",
        f"- Checked at: {checked_at}",
        f"- Acceptance status: {overall_status}",
        "",
        "## Required checks summary",
        "",
    ]
    if checks:
        for chk in checks:
            name = str(chk.get("check_name", ""))
            status = str(chk.get("status", ""))
            severity = str(chk.get("severity", ""))
            lines.append(f"- {name}: {status} ({severity})")
    else:
        lines.append("- (no checks recorded)")
    lines.append("")
    return "\n".join(lines)


def _md_pricing(offer_name: str) -> str:
    return (
        "# Pricing & Offer Checklist\n\n"
        "This is a checklist/template only. It performs no payment processing.\n\n"
        f"- Offer name: {offer_name}\n"
        "- [ ] Price confirmed\n"
        "- [ ] Scope confirmed\n"
        "- [ ] Deposit / payment status: __________ (placeholder)\n"
        "- [ ] Delivery date: __________ (placeholder)\n"
        "- [ ] Follow-up owner: __________ (placeholder)\n"
    )


def _md_followup(customer_id: str) -> str:
    return (
        "# Customer Follow-up Checklist\n\n"
        f"Follow-up flow for customer `{customer_id}`.\n\n"
        "## Day 0 handoff\n"
        "- [ ] Delivery package sent\n"
        "- [ ] Handoff note sent\n\n"
        "## Day 1 review follow-up\n"
        "- [ ] Confirm customer reviewed files\n"
        "- [ ] Collect initial feedback\n\n"
        "## Day 3 improvement request\n"
        "- [ ] Ask for any revision items\n"
        "- [ ] Log requested changes\n\n"
        "## Day 7 testimonial/referral ask\n"
        "- [ ] Request testimonial\n"
        "- [ ] Request referral\n"
    )


def _md_files_to_send(kit_files: list[str]) -> str:
    lines = [
        "# Files To Send\n",
        "## Stage 4 delivery package files",
        "",
    ]
    for name in _DELIVERY_PACKAGE_FILES:
        lines.append(f"- [ ] `{name}`")
    lines.append("")
    lines.append("## Operating kit files (this folder)")
    lines.append("")
    for name in kit_files:
        lines.append(f"- [ ] `{name}`")
    lines.append("")
    return "\n".join(lines)


def generate_first_customer_kit(
    *,
    acceptance_report_path: str | Path,
    output_dir: str | Path,
    customer_id: str,
    created_at: str,
    kit_id: str | None = None,
    customer_name: str | None = None,
    offer_name: str = "SCOS Commercial Delivery",
    overwrite: bool = False,
    copy_evidence: bool = True,
    run_manifest_path: str | Path | None = None,
) -> CustomerKitResult | CustomerKitError:
    """Generate one first customer operating kit from an accepted acceptance report.

    Expected failure states return a deterministic ``CustomerKitError``; a
    successful generation returns a ``CustomerKitResult`` and writes the kit
    folder ``<output_dir>/<kit_id>/`` with the kit manifest, operating markdown
    documents, and (optionally) copied evidence.
    """

    # --- Step 1: validate_arguments ---------------------------------------- #
    if not isinstance(customer_id, str) or not customer_id:
        return CustomerKitError.of(
            "INVALID_ARGUMENTS", "customer_id is required", "validate_arguments"
        )
    if not isinstance(created_at, str) or not created_at:
        return CustomerKitError.of(
            "INVALID_ARGUMENTS", "created_at is required", "validate_arguments"
        )
    if output_dir is None or str(output_dir) == "":
        return CustomerKitError.of(
            "INVALID_ARGUMENTS", "output_dir is required", "validate_arguments"
        )
    if acceptance_report_path is None or str(acceptance_report_path) == "":
        return CustomerKitError.of(
            "INVALID_ARGUMENTS", "acceptance_report_path is required", "validate_arguments"
        )
    for label, value in (
        ("acceptance_report_path", acceptance_report_path),
        ("output_dir", output_dir),
        ("run_manifest_path", run_manifest_path),
    ):
        if _is_url(value):
            return CustomerKitError.of(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                "validate_arguments",
                {"path": str(value), "argument": label},
            )

    resolved_customer_name = customer_name if isinstance(customer_name, str) and customer_name else customer_id
    resolved_offer_name = offer_name if isinstance(offer_name, str) and offer_name else "SCOS Commercial Delivery"

    # --- Step 2: load_acceptance_report ------------------------------------ #
    report_source = Path(str(acceptance_report_path))
    if not report_source.exists() or not report_source.is_file():
        return CustomerKitError.of(
            "INPUT_NOT_FOUND",
            "acceptance_report_path does not exist or is not a file",
            "load_acceptance_report",
            {"path": str(report_source)},
        )
    try:
        acceptance = json.loads(report_source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CustomerKitError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report is not valid JSON",
            "load_acceptance_report",
            {"path": str(report_source)},
        )
    if not isinstance(acceptance, dict):
        return CustomerKitError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report must be a JSON object",
            "load_acceptance_report",
            {"path": str(report_source)},
        )
    missing_keys = tuple(k for k in _REQUIRED_ACCEPTANCE_KEYS if k not in acceptance)
    if missing_keys:
        return CustomerKitError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report is missing required keys",
            "load_acceptance_report",
            {"missing_keys": list(missing_keys)},
        )

    checks = acceptance.get("checks")
    evidence_paths = acceptance.get("evidence_paths")
    if not isinstance(checks, list) or not isinstance(evidence_paths, list):
        return CustomerKitError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report checks and evidence_paths must be lists",
            "load_acceptance_report",
            {"path": str(report_source)},
        )

    acceptance_id = str(acceptance.get("certification_id"))
    run_id = str(acceptance.get("run_id"))
    delivery_id = str(acceptance.get("delivery_id"))
    overall_status = str(acceptance.get("overall_status"))
    checked_at = str(acceptance.get("created_at"))

    # --- Step 3: check_accepted -------------------------------------------- #
    accepted = acceptance.get("ok") is True and overall_status == "PASS"
    if not accepted:
        return CustomerKitError.of(
            "ACCEPTANCE_NOT_PASSED",
            "acceptance report is not an accepted (PASS) result",
            "check_accepted",
            {"overall_status": overall_status, "ok": bool(acceptance.get("ok"))},
        )

    # --- Step 4: resolve_sources ------------------------------------------- #
    if run_manifest_path is not None and str(run_manifest_path) != "":
        run_manifest = Path(str(run_manifest_path))
    else:
        discovered = [
            str(p)
            for p in evidence_paths
            if isinstance(p, str) and Path(p).name == _RUN_MANIFEST_FILENAME
        ]
        if not discovered:
            return CustomerKitError.of(
                "MISSING_SOURCE_ARTIFACT",
                "commercial run manifest could not be discovered from evidence_paths",
                "resolve_sources",
                {"run_manifest_filename": _RUN_MANIFEST_FILENAME},
            )
        run_manifest = Path(sorted(discovered)[0])

    if not _existing_file(run_manifest):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "commercial run manifest does not exist or is not a file",
            "resolve_sources",
            {"path": str(run_manifest)},
        )
    try:
        run_data = json.loads(run_manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "commercial run manifest is not valid JSON",
            "resolve_sources",
            {"path": str(run_manifest)},
        )
    if not isinstance(run_data, dict):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "commercial run manifest must be a JSON object",
            "resolve_sources",
            {"path": str(run_manifest)},
        )

    source_report_path = str(run_data.get("report_path") or "")
    source_package_path = str(run_data.get("package_path") or "")
    source_package_manifest_path = str(run_data.get("package_manifest_path") or "")

    if not _existing_file(source_report_path):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "commercial report file referenced by the run manifest does not exist",
            "resolve_sources",
            {"path": source_report_path},
        )
    if not _existing_dir(source_package_path):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "delivery package directory referenced by the run manifest does not exist",
            "resolve_sources",
            {"path": source_package_path},
        )
    if not _existing_file(source_package_manifest_path):
        return CustomerKitError.of(
            "MISSING_SOURCE_ARTIFACT",
            "package manifest file referenced by the run manifest does not exist",
            "resolve_sources",
            {"path": source_package_manifest_path},
        )

    # --- Step 5: prepare_output -------------------------------------------- #
    resolved_kit_id = str(kit_id) if kit_id else f"first-customer-kit-{customer_id}"
    base_dir = Path(output_dir)
    kit_folder = _fs_safe(resolved_kit_id)
    kit_dir = base_dir / kit_folder
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        resolved_base = base_dir.resolve(strict=True)
        resolved_kit = kit_dir.resolve()
    except OSError as exc:
        return CustomerKitError.of(
            "OUTPUT_WRITE_FAILED",
            "output_dir could not be prepared",
            "prepare_output",
            {"output_dir": str(base_dir), "os_error": type(exc).__name__},
        )
    if resolved_kit == resolved_base or resolved_kit.parent != resolved_base:
        return CustomerKitError.of(
            "VALIDATION_FAILED",
            "kit directory resolves outside the output directory",
            "prepare_output",
            {"kit_folder": kit_folder},
        )
    kit_dir = resolved_kit
    if kit_dir.exists() and not overwrite:
        return CustomerKitError.of(
            "OUTPUT_ALREADY_EXISTS",
            "kit output folder already exists and overwrite is False",
            "prepare_output",
            {"path": str(kit_dir)},
        )

    # --- Step 6: generate --------------------------------------------------- #
    kit_created_at = created_at
    ordered_markdown = (
        ("customer_intake_checklist.md", _md_intake(customer_id, resolved_customer_name, resolved_offer_name)),
        ("operator_sop.md", _md_sop(customer_id)),
        ("delivery_handoff.md", _md_handoff(customer_id, resolved_customer_name)),
        (
            "acceptance_certificate.md",
            _md_certificate(acceptance_id, run_id, delivery_id, checked_at, overall_status, checks),
        ),
        ("pricing_offer_checklist.md", _md_pricing(resolved_offer_name)),
        ("customer_followup_checklist.md", _md_followup(customer_id)),
    )
    # files_to_send lists every generated markdown file plus the kit manifest.
    kit_file_names = [name for name, _ in ordered_markdown] + ["files_to_send.md", _KIT_MANIFEST_FILENAME]
    markdown_files = ordered_markdown + (
        ("files_to_send.md", _md_files_to_send(sorted(kit_file_names))),
    )

    kit_files: list[CustomerKitFile] = []
    manifest_path = kit_dir / _KIT_MANIFEST_FILENAME
    try:
        kit_dir.mkdir(parents=True, exist_ok=True)

        for name, text in markdown_files:
            target = kit_dir / name
            target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")
            kit_files.append(CustomerKitFile.of(name, str(target), "markdown"))

        evidence_records: list[tuple[str, str]] = []
        if copy_evidence:
            evidence_dir = kit_dir / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            for src, label in (
                (report_source, "acceptance_report.json"),
                (run_manifest, _RUN_MANIFEST_FILENAME),
                (Path(source_package_manifest_path), "package_manifest.json"),
            ):
                dest = evidence_dir / label
                shutil.copy2(str(src), str(dest))
                evidence_records.append((label, str(dest)))
                kit_files.append(
                    CustomerKitFile.of(
                        f"evidence/{label}", str(dest), "evidence", metadata={"source_path": str(src)}
                    )
                )

        generated_files = [
            f.file_name for f in kit_files
        ] + [_KIT_MANIFEST_FILENAME]
        manifest_data = {
            "schema_version": CUSTOMER_KIT_SCHEMA_VERSION,
            "customer_id": customer_id,
            "customer_name": resolved_customer_name,
            "kit_id": resolved_kit_id,
            "acceptance_id": acceptance_id,
            "run_id": run_id,
            "delivery_id": delivery_id,
            "created_at": kit_created_at,
            "source_acceptance_report_path": str(report_source),
            "source_run_manifest_path": str(run_manifest),
            "source_report_path": source_report_path,
            "source_package_path": source_package_path,
            "source_package_manifest_path": source_package_manifest_path,
            "generated_files": sorted(generated_files),
            "metadata": {
                "generator": "scos.commercial.customer_kit",
                "overall_status": overall_status,
                "checked_at": checked_at,
                "copy_evidence": bool(copy_evidence),
                "offer_name": resolved_offer_name,
            },
        }
        manifest_path.write_text(_json_text(manifest_data), encoding="utf-8", newline="\n")
        kit_files.append(
            CustomerKitFile.of(_KIT_MANIFEST_FILENAME, str(manifest_path), "json")
        )
    except OSError as exc:
        return CustomerKitError.of(
            "OUTPUT_WRITE_FAILED",
            "customer kit files could not be written",
            "generate",
            {"kit_dir": str(kit_dir), "os_error": type(exc).__name__},
        )

    return CustomerKitResult(
        ok=True,
        schema_version=CUSTOMER_KIT_SCHEMA_VERSION,
        customer_id=customer_id,
        kit_id=resolved_kit_id,
        acceptance_id=acceptance_id,
        run_id=run_id,
        delivery_id=delivery_id,
        output_dir=str(kit_dir),
        manifest_path=str(manifest_path),
        created_at=kit_created_at,
        files=tuple(kit_files),
        metadata=FrozenMap.from_mapping(
            {
                "generator": "scos.commercial.customer_kit",
                "copy_evidence": bool(copy_evidence),
                "overall_status": overall_status,
            }
        ),
    )


__all__ = ("generate_first_customer_kit",)
