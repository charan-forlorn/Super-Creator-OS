# SCOS–HVS Integration Stage 8B — Revision Planning and Approval-Gated Re-render Contract

## Verdict

Stage 8B provides deterministic revision planning, explicit operator approval,
and a safe re-render authorization packet. It does not invoke HVS, render,
supersede the source artifact, deliver a successor version, create an invoice,
or change payment state.

## Baselines

- SCOS: `main`, starting HEAD `94026fe47c493df3bd5b9578599fa2e3184c9114`.
- HVS: `main`, read-only baseline `8e054cf368a812a12dec0d179b5374d0612bfdcd`.
- Stage 8A and [Stage 8A.1](SCOS-HVS-Integration-Stage-8A.1-delivery-version-lineage.md) are certified prerequisites.
- Python: 3.11.15. Initial collection: 1374, zero errors.

## Contract

`hvs_revision_service` creates a revision only from an accepted, integrity-verified
delivery with `REGISTERED` Stage 8A.1 lineage. It calls the Stage 8A.1 successor
planning service; it never infers or reserves a version. Each request binds the
source lineage, closure, artifact ID/SHA-256, source version, planned successor,
recipient, requester, operator, and canonical revision items.

Supported structured items include text, caption, timing, asset, audio, music,
voice, layout, branding, format, duration, compliance, technical correction, and
other changes. Logical identifiers reject traversal, paths, URLs, and shell-like
syntax. Item order is canonicalized by deterministic item ID.

Impact is derived only from item metadata. It records affected scene/asset/format
IDs and uses an explicit `UNKNOWN_REQUIRES_REVIEW` scope when insufficient data
exists. No media content is inspected.

Commercial classification is explicit: included, chargeable, warranty, internal,
commercial-review-required, or out-of-scope. Amounts reject floats and require
currency, tax, and discount. No classification creates or alters Stage 8A invoice
or payment records.

The append-only runtime ledger is
`scos/work/hvs_delivery_packages/hvs_revision_audit.jsonl`, which is ignored.
Events store immutable state snapshots for request, review, assessment,
commercial classification, plan, approval, decision, and authorization.

## State and approval boundary

`REVISION_REQUESTED → REVISION_UNDER_REVIEW → SCOPE_ASSESSED → READY_FOR_APPROVAL`
is the standard path. Chargeable/review-required classification remains blocked
at `COMMERCIAL_REVIEW_REQUIRED`. A plan binds impact and commercial hashes.
Approval binds the immutable plan, lineage, source SHA, and successor display.
Only `APPROVE_RERENDER_PLAN` creates an authorization packet.

The packet has `manual_dispatch_required=true`, `automation_allowed=false`,
`rerender_started=false`, `source_artifact_preserved=true`,
`no_overwrite_required=true`, and `supersession_status=NOT_YET_SUPERSEDED`.
It contains no command, executable arguments, path, credentials, media, or
automatic dispatch instruction.

## Implementation

- `scos/control_center/hvs_revision_models.py`
- `scos/control_center/hvs_revision_store.py`
- `scos/control_center/hvs_revision_service.py`
- `scos/control_center/cli.py`
- `scos/control_center/tests/test_hvs_revision_rerender_contract.py`

CLI commands cover request creation, review start, impact assessment, commercial
classification, plan preparation, approval request/decision, and authorization.
All emit structured JSON and remain local-only.

## Verification evidence

| Command | Result |
| --- | --- |
| Focused Stage 8B tests (`test_hvs_revision_rerender_contract.py`) | 3 passed |
| Stage 5–8A.1 regression set (all `test_hvs_*.py` except the new 8B test, cache provider disabled) | 310 passed, 1 skipped |
| Smoke tier (`scripts/test_smoke.py`) | 16 passed, 0 failed |
| pytest collection (`--collect-only`) | 1377 collected, 0 errors |
| Security scan (`scripts/security_scan_baseline.py`) | 427 files scanned, 0 findings |
| Full test suite (`pytest -q`, cache provider disabled) | 1376 passed, 1 skipped, 2 warnings |

Fresh evidence captured on Python 3.11.15 / pytest 9.1.1 during the Stage 8B
closure run. The full-suite `2 warnings` are pre-existing and unrelated to
Stage 8B: (1) a `cache_dir` pytest config option warning, and (2) a
`UnicodeDecodeError` in a subprocess reader thread inside
`test_hvs_adapter.py::test_real_hvs_readonly_help_smoke` (a read-only HVS CLI
smoke test whose captured output contains a non-UTF-8 byte). Both reproduce on
the Stage 8A.1 baseline and involve no Stage 8B module. Test-owned temporary
runtime data under `scos/work` is gitignored and is not staged.

## Scope confirmation and rollback

No HVS source was modified or invoked. No project, asset copy, media output,
render, customer contact, invoice/payment mutation, network call, dependency
change, supersession, or Stage 8C work occurred. The source delivery, closure,
lineage, and artifact are read-only inputs.

Rollback is a revert of the single Stage 8B commit. Runtime audit evidence is
append-only and remains untracked. Stage 8C may consume a valid authorization
packet only in a separate approved run.
