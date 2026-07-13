# SCOS-HVS Integration Stage 8I — Commercial Proposal Handoff

## Objective

Stage 8I converts a qualified Stage 8H commercial opportunity into a deterministic, local proposal-preparation record, internal approval evidence, and a manual commercial handoff package. It is not a proposal transport, customer-contact, invoicing, payment, CRM, publishing, rendering, or HVS integration.

## Baselines and Scope

- SCOS baseline at entry: `34d36553ef9e8bccf8db520f5b661d642392d520` on `main`.
- HVS baseline declared at entry: `8e054cf368a812a12dec0d179b5374d0612bfdcd` on `main`.
- Inputs are immutable Stage 8H opportunity/customer-outcome evidence, Stage 8G commercial-closure/dispute evidence, and Stage 8A.1 delivery lineage evidence.
- Runtime evidence is append-only JSONL at `scos/work/control_center/hvs_commercial_proposals.jsonl`; `scos/work/` is ignored.

## Contract

Conversion requires an explicitly `QUALIFIED` opportunity of type `RENEWAL`, `FOLLOW_ON_PROJECT`, `UPSELL`, or `REFERRAL` with an explicit commercial recipient. The service fails closed for a missing opportunity or lineage, non-qualified/non-commercial opportunity, missing referral recipient, invalid closure, unresolved dispute or customer concern, blocked priority, and mismatched lineage.

Proposal records require explicit scope, deliverables, exclusions, assumptions, commercial line items, currency, tax treatment, discount, payment terms, revision terms, validity dates, and operator identity. Money uses the existing decimal normalization and currency rounding. No price, discount, tax, currency, recipient, consent, eligibility, customer acceptance, or commercial term is inferred.

Allowed lifecycle transitions are:

```text
DRAFT --ready--> READY_FOR_INTERNAL_REVIEW --ready + operator approval--> APPROVED_FOR_MANUAL_PRESENTATION
  |                                                        |
  +--reject/cancel with persisted reason-------------------+
```

Readiness is read-only. It rejects invalid/pre-validity/expired evaluation dates and rechecks source eligibility. A manual handoff requires the approved state, binds the approved content hash and approval event, and explicitly records `false` for proposal sent, customer contacted, customer acceptance, invoice creation, payment-link creation, payment-state mutation, HVS invocation, and automation.

## Contract-Completeness Matrix

| Contract | Implementation | Explicit proof |
| --- | --- | --- |
| Immutable deterministic proposal and precise money | frozen models, canonical hash, decimal totals | creation, replay/conflict, changed optional-content tests |
| Input and store boundaries | bounded text, dates, recipient/container checks; schema/event validation | invalid text, money, dates, containers, malformed ledger tests |
| Qualified commercial conversion | source eligibility gate | all source blocker branches plus qualified renewal test |
| Read-only readiness | date-aware readiness result without event write | ready, missing input, pre-validity, invalid-date, expiry tests |
| Internal lifecycle | draft-only submission, approval prerequisite, terminal reason persistence | submit replay, approval, rejection, cancellation tests |
| Manual-only handoff | approved hash/event-bound package with all external-action flags false | service lifecycle and full CLI lifecycle tests |
| Deterministic review queue | local sorted queue excluding terminal proposals | queue ordering/action/exclusion test |
| CLI lifecycle | create, inspect, readiness, request review, approve, reject, cancel, handoff, queue | complete CLI lifecycle/terminal-branch test |
| Existing Stage 7–8H contracts | no edits to predecessor modules | 536-pass regression set and full suite |

The initial preserved work was partial in four places: lifecycle CLI commands and queue were absent; terminal decision reasons were not persisted; transition/date checks were incomplete; and optional commercial fields were omitted from content identity. Those behaviors are implemented and tested above. No implemented-but-untested or in-scope missing behavior remains in this stage.

## CLI Surface

- `create-hvs-commercial-proposal`
- `inspect-hvs-commercial-proposal`
- `evaluate-hvs-commercial-proposal-readiness`
- `request-hvs-commercial-proposal-review`
- `approve-hvs-commercial-proposal`
- `reject-hvs-commercial-proposal`
- `cancel-hvs-commercial-proposal`
- `create-hvs-manual-commercial-handoff`
- `list-hvs-commercial-proposal-review-queue`

Each emits structured local JSON. Mutating commands write only the ignored local Stage 8I ledger. No command contacts a customer or invokes HVS.

## Final Verification

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8i scos/control_center/tests/test_hvs_commercial_proposal_handoff.py -q -rA` | 25 passed, 0 failed, exit 0, 6.51s |
| Direct synthetic lifecycle acceptance in `test_qualified_renewal_converts_then_requires_readiness_and_operator_approval` | qualified renewal → readiness → review → approval → manual handoff; local-only flags proved false |
| Stage 7 plus pre-8I HVS regression set | 536 passed, 1 skipped, 0 failed, exit 0, 44.62s |
| `.venv\Scripts\python.exe scripts\test_smoke.py` | 16 passed, 0 failed, exit 0 |
| `.venv\Scripts\python.exe -m pytest --collect-only -q` | 1,609 collected, 0 errors, exit 0, 0.96s |
| `.venv\Scripts\python.exe scripts\security_scan_baseline.py` | 455 files scanned, 0 findings, exit 0 |
| `.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8i-full-final -q` | 1,608 passed, 1 skipped, 0 failed, exit 0, 347.09s |

Every pytest invocation emitted the pre-existing non-fatal cache warning for the permission-denied path `scos/work/.pytest_cache`; it was neither changed nor cleaned.

## Security and Scope Boundary

The implementation imports no HVS runtime/adapter module and uses no subprocess, network library, customer transport, CRM, payment provider, invoice mutation, payment mutation, publishing, upload, or rendering code. It writes only local append-only proposal evidence. The tests prove external-action fields remain false.

## Limitations and Rollback

Stage 8I ends at manual-presentation authorization. It does not send, present, accept, invoice, collect payment, or record a customer decision. Roll back only by reverting the Stage 8I commit; predecessor ledgers are unchanged and proposal-ledger records are append-only.

## Verdict

Stage 8I is contract-complete and locally certified: qualified commercial opportunities can be prepared, reviewed, approved/rejected/cancelled, placed in a deterministic review queue, and handed off manually without external action.
