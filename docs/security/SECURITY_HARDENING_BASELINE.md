# SCOS Security Hardening Baseline (Stage 4.18)

This document records the security baseline for the Stage 4 commercial
foundation and the hardening items handed to Stage 5. Stage 4.18 implements
only local, deterministic tooling (checksums, static scan); everything else
here is a documented plan, not implemented behavior.

## 1. Artifact integrity verification

- Every commercial artifact written by a stage is referenced from a manifest
  with a deterministic path and, where applicable, a SHA-256 digest.
- Shared tooling: `scos.commercial.manifest_tools` (`sha256_file`,
  `sha256_text`, `build_artifact_record`, `ChecksumCache`). Digests use
  streaming 64 KiB chunked reads and are byte-stable across runs.
- Verification procedure: recompute `sha256_file` for each manifest entry
  and compare; any mismatch is a blocker (`CommercialBlocker`, category
  `integrity`, severity `critical`).

## 2. Manifest checksum baseline

- Manifests are serialized with `stable_json_dumps` (sorted keys, 2-space
  indent, trailing newline, LF) so the manifest itself has a stable digest.
- A manifest's own SHA-256 can therefore serve as a release fingerprint;
  Stage 4.19 should record it in the gate evidence.
- `build_manifest_metadata` standardizes the metadata block
  (`schema_version`, `created_at` (caller-supplied, never a live clock),
  `generator`, `source_hash`, `metadata`).

## 3. Immutable audit log design (design only)

- Append-only JSON Lines file per stage run; each record carries the record
  payload plus the SHA-256 of the previous record, forming a local hash
  chain (tamper-evidence without any server).
- Records are never rewritten; corrections append a superseding record.
- Not implemented in Stage 4.18; Stage 5 implements it alongside the
  Control Center command boundary (every dispatched command gets a chained
  audit record).

## 4. Dependency vulnerability scan plan (plan only)

- Runtime commercial code is stdlib-only; the third-party surface is
  `requirements.txt` (`mcp`, `numpy`) plus the UI toolchain.
- Plan: pin exact versions (already done), review advisories for the pinned
  set at each release gate, and record the review in the gate evidence.
  Automated scanners (e.g. `pip-audit`) may be adopted in Stage 5; Stage 4
  performs the review manually and offline.

## 5. Secret scanning baseline

- Implemented: `scripts/security_scan_baseline.py` — local static scan of
  commercial executable source, scripts, and root config files for
  credential/token indicators, private key headers, and committed
  environment files. No network, no external scanners, redacted samples
  only, deterministic output, exit 1 on any finding.
- Run at minimum as part of the release tier (`scripts/test_release.py`).

## 6. SBOM baseline (plan only)

- The effective SBOM today is `requirements.txt` (pinned) plus the Python
  interpreter version recorded in its header.
- Plan: Stage 5 generates a formal SBOM (CycloneDX or SPDX JSON) at release
  time and stores it with the release manifest, checksummed like any other
  artifact (section 1).

## 7. Release provenance checklist

For every release candidate the operator records:

1. `git rev-parse HEAD` and confirmation `HEAD == origin/main`.
2. Clean `git status --porcelain`.
3. Release tier result (`scripts/test_release.py` exit 0).
4. Security scan result (`scripts/security_scan_baseline.py` exit 0).
5. SHA-256 of every release manifest (section 2).
6. The operator identity and the `created_at` timestamp recorded in the
   manifest metadata.

No signing infrastructure exists in Stage 4.18; cryptographic signing of
the provenance record is a Stage 5 item (section 10).

## 8. Manual-only commercial boundary

- Stage 4 commercial flows are manual-only: the system prepares artifacts;
  a human performs every outward-facing action.
- Enforced in code by `scos.commercial.validation.validate_manual_only_flags`,
  which rejects enabled automation/external-service flags (auto-send,
  relationship-sync, money-capture, network/SaaS/scraping/LLM flags), and by
  the per-stage `MANUAL_ONLY_VIOLATION` error kinds.
- Sensitive personal data is rejected from metadata by
  `validate_no_sensitive_metadata` (phone/email/address/identity/financial
  field names).

## 9. No payment/billing/CRM behavior in Stage 4

Stage 4 contains no payment capture, billing sync, invoice generation, CRM
sync, SaaS/portal, network, scraping, or LLM behavior — these words appear
in code only as forbidden-flag names (assembled from fragments) and in docs
as non-goals. The static scan (section 5) checks executable source for
provider imports and network libraries; docs are exempt by design.

## 10. Stage 5 security handoff items

1. Implement the immutable audit log (section 3) under the Control Center
   command boundary.
2. Add authenticated local operator identity for command approval
   (`operator_approval` in `docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md`).
3. Adopt automated dependency scanning (section 4) and SBOM generation
   (section 6) in the release pipeline.
4. Add cryptographic signing of release provenance records (section 7).
5. Re-run this baseline document review whenever any network-facing
   capability is introduced; anything network-facing requires its own
   threat model first.
