# SCOS–HVS Integration Stage 8A.1 — Immutable Delivery-Version Lineage

## Objective and prerequisite

Stage 8A.1 closes the contract gap that prevented Stage 8B from safely using a
prior delivery as a revision source.  The existing Stage 8A certification is
closed and remains unchanged: it records that invoice preparation and payment
follow-up are manual only.  This stage adds an independent, immutable lineage
ledger.  It does not implement Stage 8B revision planning or re-render
authorization.

| Baseline | Evidence |
| --- | --- |
| SCOS root / branch | `C:\Workspace\super-creator-os` / `main` |
| SCOS starting HEAD | `9482061a417a84a66641c72b69faebcc4b79990c` |
| HVS root / branch | `C:\Workspace\hermes-video-studio` / `main` |
| HVS baseline HEAD | `8e054cf368a812a12dec0d179b5374d0612bfdcd` |
| Python | `3.11.15` |
| Stage 8A evidence | `docs/certification/SCOS-HVS-Integration-Stage-8A-manual-invoice-payment-follow-up.md` |

The Stage 5–8A delivery contracts already provide a deterministic manual
delivery record, accepted closure ID, project ID, artifact SHA-256, recipient
label, and invoice linkage.  They do not contain a certified delivery version,
parent version, successor version, immutable artifact lineage, or supersession
state.  Automatically assigning legacy records `v1` would therefore be an
unsupported inference and is prohibited.

## Contract

`DeliveryVersion` is a positive integer sequence.  Its canonical display is
always `v<sequence>`; accepted input is an integer or the explicitly documented
string forms `N` and `vN`, without leading zeros, signs, decimals, floats,
zero, or negatives.  Timestamps never affect version identity.

Completed deliveries without a lineage event are exposed through a derived
read view as:

```json
{
  "lineage_status": "UNKNOWN",
  "registered_version": null,
  "successor_planning_eligible": false,
  "blocking_reason": "DELIVERY_VERSION_UNKNOWN"
}
```

UNKNOWN does not invalidate a manual delivery, accepted closure, invoice, or
payment record.  It only blocks version-dependent operations.

Successful registrations create a frozen `DeliveryLineageRecord` bound to the
project, recipient label, manual delivery record, accepted closure, deterministic
artifact ID, artifact SHA-256, normalized version, optional parent lineage, and
operator basis.  `lineage_id` is derived from project/delivery/closure/artifact
identity/version/parent content only; it excludes timestamps, paths, machine
state, notes, and event order.  The stored deterministic content hash excludes
the informational registration timestamp.

This stage uses `NOT_YET_SUPERSEDED`: it expresses that a later version may be
planned but does not mark the source or artifact superseded.  No transition to
`SUPERSEDED` exists in Stage 8A.1.

## Registration and uniqueness rules

Every legacy registration requires an operator ID, explicit version, a bounded
registration basis, and `--confirm-legacy-version`.  Allowed bases are:

- `ORIGINAL_DELIVERY_CONFIRMED` — only for explicitly confirmed `v1`.
- `EXISTING_EXTERNAL_VERSION_RECORD` — requires a non-sensitive evidence reference.
- `OPERATOR_HISTORICAL_RECONCILIATION` — requires a reconciliation reason.
- `IMPORTED_CERTIFIED_LINEAGE` — requires a registered parent and evidence reference; a documented historical sequence gap is permitted only here.
- `SUCCESSOR_OF_REGISTERED_DELIVERY` — requires a registered parent.

Within one project, a delivery record, version sequence, and artifact SHA-256
each map to one immutable lineage.  Registration replay with identical semantic
content is idempotent.  A conflicting delivery, version, artifact, parent,
cycle, or non-immediate successor is rejected; an imported certified lineage is
the sole documented exception for a sequence gap.  Parent versions must be
strictly lower, so a cycle cannot be created.

Registration is allowed only after the Stage 7 closure is accepted and its
artifact is revalidated through the existing closure integrity check.  It never
rewrites the manual delivery record, closure record, artifact, invoice event, or
payment event.

## Storage and service API

Runtime state is append-only JSONL at:

`scos/work/hvs_delivery_packages/hvs_delivery_lineage.jsonl`

The parent runtime tree is already ignored by `.gitignore`.  One canonical JSON
object is written per event.  Duplicate identical event IDs replay safely;
conflicting duplicate IDs and malformed lines fail closed.  The store rejects
URL and traversal paths; the CLI provides no store-path argument.

Events are `LINEAGE_REGISTRATION_REQUESTED`, `LINEAGE_REGISTERED`,
`LINEAGE_REGISTRATION_REJECTED`, `LINEAGE_CONFLICT_DETECTED`, and the reserved
`SUCCESSOR_VERSION_PLANNED`.  Pure planning does not write an event or reserve
a version.

The service API is:

- `inspect_delivery_lineage`
- `register_delivery_lineage`
- `verify_lineage_integrity`
- `derive_successor_version`
- `plan_successor_version`
- `list_project_delivery_lineage`
- `inspect_lineage_events`

`derive_successor_version` is a pure operation.  A registered `vN` returns
`v(N+1)` with `persistence_performed=false`, `rerender_started=false`, and
`automation_allowed=false`.  UNKNOWN returns `DELIVERY_VERSION_UNKNOWN`.

## CLI

```powershell
python -m scos.control_center.cli inspect-hvs-delivery-lineage --delivery-record-id <id>
python -m scos.control_center.cli register-hvs-delivery-lineage --delivery-record-id <id> --delivery-version 1 --registration-basis original_delivery_confirmed --operator-id <operator> --confirm-legacy-version
python -m scos.control_center.cli plan-hvs-successor-version --delivery-record-id <id>
python -m scos.control_center.cli list-hvs-delivery-lineage --project-id <id>
```

All commands emit structured JSON.  Inspect returns exit 0 for an existing
completed delivery even when lineage is UNKNOWN; registration and successor
planning return non-zero for their explicit error states.

## Direct synthetic acceptance evidence

The following acceptance record used only ignored SCOS runtime state and never
opened or modified HVS:

| Item | Value |
| --- | --- |
| Delivery record | `scos-hvs-delivery-rec-46ec0472c5ee3c7f` |
| Closure | `scos-hvs-closure-e3c1f42d17ba1d1f` |
| Artifact SHA-256 | `ff936936810fa3fc0274b354d32bdcc2bb5763d69674e0aed698de78e5a6025a` |
| Registered lineage | `scos-hvs-lineage-cf4c323bf26084a8` |
| Registration content hash | `bba0b20aa4ea944eea99725b4067dee061c3a9289d06aaa8d9f08fc88cb0808c` |

1. `inspect-hvs-delivery-lineage` returned exit 0 with `UNKNOWN`, version
   `null`, eligibility `false`, and `DELIVERY_VERSION_UNKNOWN`.
2. Registration without `--confirm-legacy-version` returned exit 1 with
   `LEGACY_VERSION_CONFIRMATION_REQUIRED` and wrote no successful record.
3. Explicit `ORIGINAL_DELIVERY_CONFIRMED` registration of version 1 returned
   exit 0 with `REGISTERED`, `v1`, the SHA above, and
   `NOT_YET_SUPERSEDED`.
4. `plan-hvs-successor-version` returned exit 0 with `v2`,
   `persistence_performed=false`, `rerender_started=false`, and no
   supersession.
5. A second registration of the same delivery as a successor returned exit 1
   with `LINEAGE_CONFLICT` (`successor must bind a distinct artifact SHA-256`).
   The original `v1` record remained unchanged.

The focused tests independently verify delivery/closure/artifact immutability,
append-only events, no persistence during planning, no revision request, no
authorization packet, and invoice/payment non-interference.

## Verification

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_hvs_delivery_version_lineage.py -q` | 10 passed |
| Focused Stage 5–8A regression command | 105 passed, 1 skipped, 1 warning |
| `.\.venv\Scripts\python.exe -m pytest scos/control_center/tests -q -rA` | 943 passed, 1 skipped, 1 warning, 86.19s |
| `.\.venv\Scripts\python.exe -m pytest --collect-only -q` | 1374 collected, 0 errors, 0.87s |
| `.\.venv\Scripts\python.exe -m pytest -q -rA` | 1373 passed, 1 skipped, 1 warning, 334.83s |
| `.\.venv\Scripts\python.exe scripts\test_smoke.py` | 16 passed, 0 failed |
| `.\.venv\Scripts\python.exe scripts\security_scan_baseline.py` | PASS; 423 files; 0 findings |

The sole pytest warning is environmental: the configured cache directory
`scos/work/.pytest_cache` is denied by the Windows sandbox.  Tests used a
workspace-local base temp directory; the generated directory was removed before
the commit gate.  The warning does not represent a test failure.

Static review of changed production files found no `subprocess`, shell,
network, HVS CLI, render, project creation, artifact overwrite, invoice, or
payment mutation capability.  No dependency or lock-file changes were made.

## Compatibility, limits, and rollback

Existing callers that do not request lineage are unchanged.  Manual delivery,
closure, invoice, payment, and prior audit records are not rewritten.  Stage
8A.1 neither creates a revision request nor assesses revision scope, invokes
HVS, renders, creates an authorization, supersedes an artifact, or changes
invoice/payment state.

Known limits: no automatic legacy migration, no semantic versions, no inferred
timestamps/filename ordering, no historical parent fabrication, and no Stage 8B
workflow.  To roll back the code, revert the single Stage 8A.1 commit; existing
append-only runtime lineage evidence remains intact and unmodified.  Runtime
records are ignored and were not staged or committed.

## Readiness verdict

Stage 8A.1 provides explicit immutable delivery-version lineage and deterministic
successor-version planning.  Legacy deliveries remain UNKNOWN until an operator
explicitly registers a version.  This stage does not create revision requests,
invoke HVS, render, supersede artifacts, or modify invoice/payment state.

**Verdict: ready as the certified lineage baseline for a separate Stage 8B run.**
