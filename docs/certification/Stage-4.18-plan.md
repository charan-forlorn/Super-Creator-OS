# Stage 4.18 — Commercial Core Hardening & Platform Foundation (Plan)

## Stage goal

Harden the existing Stage 4 commercial foundation with shared, reusable
infrastructure: common immutable domain models, unified validation helpers,
stable manifest/checksum tooling, a documented test-tier strategy, a security
hardening baseline, and design-only specifications for the Stage 5 Control
Center command API and shared reporting framework. Maintainability,
validation consistency, artifact integrity, test-speed strategy, and
security readiness improve without breaking any Stage 4.1–4.17 public
contract.

## Scope

- Add `scos/commercial/domain_models.py`, `validation.py`,
  `manifest_tools.py` as shared support utilities (stdlib-only,
  deterministic, local-first) with plain-assert test suites.
- Add smoke/release/security scripts under a new `scripts/` directory.
- Document the four-tier test strategy and the security hardening baseline.
- Design-only documents for the Control Center command API and the shared
  reporting framework.
- Register new exports lazily in `scos/commercial/__init__.py` (PEP 562
  architecture preserved; no eager imports; no knowledge import at package
  import time).

## Non-goals

- No new commercial feature flow; no Stage 4.20+.
- No backend/API server, database, WebSocket, polling, real agent dispatch,
  or Control Center live integration (design only).
- No CRM, payment, billing, invoice generation, SaaS, customer portal,
  network/cloud behavior, or LLM calls.
- No refactor/migration of Stage 4.1–4.17 modules onto the new helpers, and
  no change to any of their serialized outputs.
- No Certified Core changes; no `scos/knowledge` implementation changes.
- No signing or release-provenance implementation (checklist/docs only).

## Files created

- `scos/commercial/domain_models.py` — `COMMERCIAL_DOMAIN_SCHEMA_VERSION`,
  `CommercialCheck`, `CommercialBlocker`, `CommercialArtifactReference`,
  `CommercialManualAction` (frozen dataclasses, `of()` factories,
  deterministic `to_dict()`, FrozenMap metadata, enum validation).
- `scos/commercial/validation.py` — `COMMERCIAL_VALIDATION_SCHEMA_VERSION`,
  required-key / URL / local-path / existing-file / existing-dir checks,
  recursive sensitive-metadata scan, manual-only flag detection, path
  containment, safe JSON object loading.
- `scos/commercial/manifest_tools.py` —
  `COMMERCIAL_MANIFEST_TOOLS_SCHEMA_VERSION`, `stable_json_dumps`,
  `write_stable_json`, `sha256_text`, `sha256_file`,
  `build_artifact_record`, `build_manifest_metadata`, `ChecksumCache`.
- `scos/commercial/tests/test_domain_models.py`
- `scos/commercial/tests/test_validation.py`
- `scos/commercial/tests/test_manifest_tools.py`
- `scripts/test_smoke.py`, `scripts/test_release.py`,
  `scripts/security_scan_baseline.py`
- `docs/testing/TEST_SUITE_STRATEGY.md`
- `docs/security/SECURITY_HARDENING_BASELINE.md`
- `docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md` (design only)
- `docs/specification/SHARED_REPORTING_FRAMEWORK_CONTRACT.md` (contract only)
- `docs/certification/Stage-4.18-plan.md` (this file)

Modified (lazy exports only): `scos/commercial/__init__.py`.

## Tests required

Primary (all expect `RESULT: N passed, 0 failed`, exit 0):

```
.venv\Scripts\python.exe scos\commercial\tests\test_domain_models.py
.venv\Scripts\python.exe scos\commercial\tests\test_validation.py
.venv\Scripts\python.exe scos\commercial\tests\test_manifest_tools.py
```

Scripts (exit 0):

```
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
.venv\Scripts\python.exe scripts\test_release.py
```

Import safety:

```
.venv\Scripts\python.exe -c "import sys, scos.commercial as c; assert c.COMMERCIAL_DOMAIN_SCHEMA_VERSION == 1; assert not any(m.startswith('scos.knowledge') for m in sys.modules)"
```

## Regression strategy

Representative Stage 4 suites must exit 0 unchanged:

- `scos/commercial/tests/test_report_builder.py`
- `scos/commercial/tests/test_delivery_package.py`
- `scos/commercial/tests/test_cli.py`
- `scos/commercial/tests/test_first_customer_conversion_handoff.py`

`scripts/test_release.py` runs this same set as embedded regression via
subprocess.

## Security scan baseline

`scripts/security_scan_baseline.py` statically scans commercial executable
source, scripts, and root config files for token/credential indicators,
money-provider imports, network libraries in commercial source,
external-service indicators, committed env files, and private key headers.
Docs are exempt (they name forbidden capabilities as non-goals). All scan
patterns are assembled from string fragments so the scanner and the
validation module never flag themselves. Expected: `SECURITY SCAN: PASS`,
0 findings.

## No public contract break rule

Stage 4.18 is additive-only: no existing export, dataclass field, error
kind, file format, or serialized output of Stage 4.1–4.17 changes. The
lazy-export architecture and every existing `_LAZY_EXPORTS`/`__all__` entry
are preserved verbatim; new names are appended.

## No backend/API rule

Stage 4.18 implements no API routes, server, database, WebSocket, polling,
or live Control Center integration. `CONTROL_CENTER_COMMAND_API_DESIGN.md`
is design-only for Stage 5.

## Stage 4.19 handoff

Stage 4.19 (Final Commercial Release Gate & Stage 5 Handoff) receives:

- `scripts/test_release.py` as the gate entry point, with explicit
  `TODO(Stage 4.19)` hooks (full test directory, certification-tier
  evidence, HEAD/origin verification, provenance checklist, machine-readable
  gate report).
- The four-tier strategy in `docs/testing/TEST_SUITE_STRATEGY.md` as the
  gating skeleton.
- The security baseline and its Stage 5 handoff items in
  `docs/security/SECURITY_HARDENING_BASELINE.md`.
- Shared domain models / validation / manifest tooling for the gate's own
  report, checks, and artifact fingerprints.

## No commit / push rule

Implement, test, and report only. **No commit, push, tag, or release.** No
pull/merge/rebase/reset/stash/clean/branch-switch. If unexpected dirty files
appear, stop and report.
