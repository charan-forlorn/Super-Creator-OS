# SCOS-HVS Integration Stage 8J - Commercial Acceptance Gate

## Purpose and Business Value

Stage 8J records a proposal presentation performed manually by a human
operator, records explicit customer commercial-decision evidence, and verifies
whether an exact accepted proposal is ready for future manual invoice
preparation and manual project kickoff.

This stage authorizes only future human-controlled workflows. It does not send
proposals, contact customers, issue invoices, create payment links, collect
payment, invoke HVS, render media, publish artifacts, create CRM tasks, or begin
Stage 8K.

## Certified Starting Baseline

- SCOS starting baseline: `bbfc2d525cedacf2e6a63c333dc4cb9444b57f1d`
- SCOS branch: `main`
- HVS read-only baseline: `8e054cf368a812a12dec0d179b5374d0612bfdcd`
- HVS branch: `main`
- Stage 8I prerequisite: closed by
  `feat(integration): add operator-controlled commercial handoff gate`

The final commit hash is the single local commit containing this certification
document and is recorded by the post-commit verification command
`git log -1 --format="%H%n%h%n%s"` in the Stage 8J closure report.

## Architecture Boundary

Allowed flow:

```text
Stage 8I approved proposal
-> operator-confirmed manual presentation record
-> operator-supplied customer decision evidence
-> deterministic exact-acceptance validation
-> commercial acceptance record
-> READY_FOR_MANUAL_INVOICE_AND_KICKOFF
```

Prohibited flow:

```text
proposal -> automated transport -> customer signature/payment/project/render
```

Stage 8J is an evidence and authorization contract. It is not a
communication, signature, payment, invoice, CRM, project-creation, render, or
HVS integration system.

## Presentation Contract

`ProposalPresentationRecord` is created only for an existing Stage 8I proposal
with status `APPROVED_FOR_MANUAL_PRESENTATION` and a matching manual commercial
handoff package. The record binds:

- proposal preparation ID
- commercial handoff package ID
- approved proposal content hash
- opportunity, commercial scope, project, customer, delivery-lineage and
  artifact SHA-256 lineage
- manual presentation channel and supplied date
- explicit operator identity
- optional bounded evidence, participant reference and operator note

`manual_action_confirmed` is required. `communication_performed_by_system` and
`automation_allowed` are always false.

## Customer Decision Contract

`CustomerDecisionRecord` supports:

- `ACCEPTED`
- `REJECTED`
- `NEGOTIATION_REQUESTED`
- `PROPOSAL_REVISION_REQUESTED`
- `NO_RESPONSE`
- `DEFERRED`

Every decision requires a prior presentation, explicit operator identity,
explicit decision date, explicit evidence reference and the exact approved
proposal content hash. No decision is inferred from silence, elapsed time,
payment state, transport state or customer identity.

## Exact Acceptance Rules

An accepted decision creates a commercial acceptance only when all accepted
commercial values exactly match the approved Stage 8I proposal:

- content hash
- total
- currency
- commercial scope hash
- tax
- discount
- payment terms
- revision terms
- proposal validity on the decision date

Any changed price, currency, scope, tax, discount, payment terms, revision
terms, requested change or partial acceptance blocks exact acceptance and must
be handled as negotiation or proposal revision rather than normalized into
acceptance.

## Commercial Acceptance Contract

`CommercialAcceptanceRecord` is persisted only for a valid exact accepted
decision. It binds the decision, presentation, proposal, handoff, approved
content hash, accepted scope hash, source opportunity, commercial scope, source
delivery lineage, artifact ID, artifact SHA-256, monetary totals, currency,
payment terms, revision terms, evidence reference and operator.

The safety flags are explicit and false:

- `invoice_created`
- `payment_link_created`
- `payment_state_changed`
- `project_created`
- `hvs_invoked`
- `render_started`
- `customer_contact_performed_by_system`
- `automation_allowed`

`ready_for_manual_invoice`, `ready_for_manual_project_kickoff`,
`manual_invoice_required` and `manual_project_kickoff_required` are true only
after `ACCEPTED_VERIFIED`.

## Readiness Rules

Readiness evaluation is deterministic and read-only. It reports:

- `READY_FOR_MANUAL_INVOICE_AND_KICKOFF`
- `NEEDS_OPERATOR_INPUT`
- `BLOCKED`
- `NOT_ACCEPTED`
- `EXPIRED`
- `NEGOTIATION_REQUIRED`

It returns blockers, warnings, missing fields, an acceptance ID when available,
manual-action recommendations and all no-external-action safety flags. It does
not mutate records and does not read the current clock.

## Deterministic IDs

Identities are derived from immutable semantic inputs only:

- Presentation IDs bind proposal, approved hash, handoff, project/customer,
  channel, date, operator and evidence reference.
- Decision IDs bind presentation, proposal, approved hash, decision type, date,
  explicit decision semantics and evidence reference.
- Acceptance IDs bind decision, presentation, proposal, approved hash, scope,
  monetary values, currency, commercial scope and artifact SHA-256.

Current timestamp, process ID, machine name, temp path, runtime directory, event
ordering and non-semantic notes are excluded from identity.

## Append-Only Audit Behavior

Stage 8J writes an ignored append-only runtime ledger at:

`scos/work/hvs_delivery_packages/hvs_commercial_acceptance.jsonl`

The parent `scos/work/` tree is ignored by Git. Store reads reject malformed
JSONL, duplicate event IDs, unsafe URL paths and path traversal. Identical
replay is idempotent. Conflicting replay is rejected. Prior Stage 8H and 8I
records are not rewritten.

## Security and Privacy Boundaries

Stage 8J production modules import no HVS package, use no subprocess, use no
shell execution, use no network libraries and perform no customer transport.
Evidence references are bounded safe identifiers; secret-like and raw private
message markers are rejected or omitted from persisted output.

No customer contact, proposal transmission, e-signature action, invoice
creation, payment mutation, HVS invocation, render, upload, publish or external
task creation is implemented.

## Verification

| Gate | Command | Result |
| --- | --- | --- |
| Focused Stage 8J | `.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8j scos/control_center/tests/test_hvs_commercial_acceptance_gate.py -q -rA` | 43 passed, 0 failed, 1 warning, exit 0, 13.66s |
| Affected Stage 7-8I regressions | `.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8j-regression scos/control_center/tests/test_hvs_commercial_acceptance_gate.py scos/control_center/tests/test_hvs_commercial_proposal_handoff.py scos/control_center/tests/test_hvs_customer_outcome_consent_opportunity.py scos/control_center/tests/test_hvs_delivery_closure.py scos/control_center/tests/test_hvs_invoice_payment_follow_up.py scos/control_center/tests/test_hvs_post_delivery_support_authorization.py scos/control_center/tests/test_hvs_revenue_audit_summary.py -q -rA` | 180 passed, 0 failed, 1 warning, exit 0, 43.29s |
| Smoke | `.venv\Scripts\python.exe scripts\test_smoke.py` | 16 passed, 0 failed, exit 0 |
| Collection | `.venv\Scripts\python.exe -m pytest --collect-only -q` | 1,652 collected, 0 errors, exit 0, 0.99s |
| Security | `.venv\Scripts\python.exe scripts\security_scan_baseline.py` | 459 files scanned, 0 findings, exit 0 |
| Full suite | `.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8j-full -q -rA` | 1,651 passed, 1 skipped, 0 failed, 1 warning, exit 0, 398.93s |
| Diff check | `git diff --check` | pass with known LF-to-CRLF warning for `scos/control_center/cli.py` |

The only warning observed was the pre-existing non-fatal pytest cache warning
for the permission-denied path `scos/work/.pytest_cache`.

## Acceptance Evidence

Focused tests prove:

- exact accepted decision creates `ACCEPTED_VERIFIED`
- negotiation and proposal revision paths create no acceptance
- rejection and no-response paths create no acceptance
- content-hash, scope, total, currency, tax, discount, payment-term and
  revision-term mismatches block acceptance
- readiness becomes `READY_FOR_MANUAL_INVOICE_AND_KICKOFF` only after verified
  exact acceptance
- invoice, payment, project, HVS, render and customer-contact flags remain
  false

## HVS Status

HVS was inspected read-only at `8e054cf368a812a12dec0d179b5374d0612bfdcd` on
`main`; its working tree was clean and `git diff --check` passed. No HVS files
were modified, imported, invoked or rendered.

## Known Limitations

Stage 8J does not certify customer signatures, legal enforceability, invoice
issuance, payment collection, customer communication, project kickoff or HVS
execution. Those remain future human-controlled workflows.

## Stage 8K

Stage 8K was not started.
