"""SCOS <-> Hermes Video Studio (HVS) — Stage 3 Evidence CLI.

Local-only, deterministic ``argparse`` front-end over
``scos.control_center.hvs_evidence_intake.intake_hvs_render_evidence``.
It emits a structured JSON decision packet and returns:

* exit 0  — only for a VERIFIED export-ready packet
* exit 1  — invalid / failed / untrusted evidence
* exit 2  — argparse usage error

It does NOT auto-trigger any downstream command, does NOT write
evidence, and does NOT import or invoke HVS.

Entry point::

    python -m scos.control_center.cli inspect-hvs-render-evidence \
        --evidence-path <path> [--no-verify-artifact]

Boundary: the intake module is imported lazily; this file only
knows the explicit command surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COMMNAD_NAME = "inspect-hvs-render-evidence"
CLI_SCHEMA_VERSION = 1

# Exit codes (stable, machine-readable).
EXIT_OK = 0
EXIT_REJECT = 1
EXIT_USAGE = 2


class _CliError(Exception):
    """Expected, deterministic failure. Rendered as failure JSON, exit 1."""

    def __init__(
        self,
        error_kind: str,
        error_detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_detail)
        self.error_kind = error_kind
        self.error_detail = error_detail
        self.metadata = dict(metadata or {})


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False))


def _reject_url(*paths: Any) -> None:
    for path in paths:
        if path is None:
            continue
        text = str(path)
        if text.startswith("http://") or text.startswith("https://"):
            raise _CliError(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                {"path": text},
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scos.control_center.cli",
        description="SCOS Stage 3 HVS render-evidence intake CLI "
        "(local-only, deterministic).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        COMMNAD_NAME,
        help="Ingest an HVS Stage 6 render-validation evidence file "
        "and emit a deterministic operator decision packet.",
    )
    p.add_argument("--evidence-path", required=True)
    p.add_argument(
        "--no-verify-artifact",
        action="store_true",
        help="Do NOT re-check the artifact's SHA-256 against the evidence "
        "(degrades trust to PARTIAL; never falsely VERIFIED).",
    )
    p.set_defaults(func=_cmd_inspect)
    return parser


def _cmd_inspect(args: argparse.Namespace) -> int:
    command = COMMNAD_NAME
    _reject_url(args.evidence_path)
    from .hvs_evidence_intake import intake_hvs_render_evidence

    verify_artifact = not args.no_verify_artifact
    result = intake_hvs_render_evidence(
        evidence_path=args.evidence_path,
        verify_artifact=verify_artifact,
    )
    _emit(result.to_dict())
    # exit 0 ONLY for a verified export-ready packet.
    if result.ok and result.trust_level == "VERIFIED":
        return EXIT_OK
    return EXIT_REJECT


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)  # argparse usage errors exit 2
    func = getattr(args, "func", None)
    if func is None:
        _emit({
            "ok": False,
            "command": getattr(args, "command", None),
            "schema_version": CLI_SCHEMA_VERSION,
            "error_kind": "INVALID_COMMAND",
            "error_detail": "unknown or unsupported command",
        })
        return EXIT_REJECT
    try:
        return func(args)
    except _CliError as exc:
        _emit({
            "ok": False,
            "command": getattr(args, "command", None),
            "schema_version": CLI_SCHEMA_VERSION,
            "error_kind": exc.error_kind,
            "error_detail": exc.error_detail,
            "metadata": exc.metadata,
        })
        return EXIT_REJECT


if __name__ == "__main__":
    sys.exit(main())
