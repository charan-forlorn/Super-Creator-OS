# SCOS-HVS Integration Stage 8K Certification

## Stage title and scope

Stage 8K - Commercial Engagement Activation, Payment/Deposit Readiness, and Production Kickoff Authorization Gate.

This stage converts a verified Stage 8J commercial acceptance into a deterministic, local-only engagement activation record and a local production-kickoff authorization package. The final Stage 8K state authorizes only a future human-controlled Stage 8L project-initialization action.

Stage 8K does not create an HVS project, invoke HVS, render, copy production assets, contact customers, issue invoices, create payment links, process payment, or begin Stage 8L.

## Starting SCOS baseline

* Starting SCOS baseline: `eadcc0759df9a7fc3b76a7a4bfc63135c3761d3b`
* Starting branch: `main`
* Starting SCOS state: clean, no staged files
* Stage 8J certified capability: Manual Proposal Presentation, Customer Decision Recording, and Commercial Acceptance Gate

## HVS read-only baseline

* HVS repository: `C:\Workspace\hermes-video-studio`
* HVS branch: `main`
* HVS HEAD before Stage 8K: `8e054cf368a812a12dec0d179b5374d0612bfdcd`
* HVS mode: read-only inspection only

## Architecture boundary

Allowed flow:

`Stage 8J commercial acceptance -> eligibility re-verification -> engagement activation -> explicit payment/deposit requirement record -> explicit customer-input readiness record -> deterministic readiness evaluation -> operator review -> explicit approval/rejection/cancellation -> local kickoff authorization package`

Forbidden flow:

`engagement activation -> invoice/payment provider/customer communication/HVS project creation/asset copy/render/upload/publish`

## Files created and modified

Created:

* `scos/control_center/hvs_engagement_activation_models.py`
* `scos/control_center/hvs_engagement_activation_service.py`
* `scos/control_center/hvs_engagement_activation_store.py`
* `scos/control_center/tests/test_hvs_engagement_activation_kickoff.py`
* `docs/certification/SCOS-HVS-Integration-Stage-8K-engagement-activation-kickoff.md`

Modified:

* `scos/control_center/cli.py`

## Commercial-acceptance eligibility contract

Engagement activation requires an existing Stage 8J `ACCEPTED_VERIFIED` commercial acceptance. The Stage 8K service re-verifies:

* accepted proposal status is `APPROVED_FOR_MANUAL_PRESENTATION`
* proposal content hash matches the handoff, presentation, decision, and acceptance
* presentation was manually confirmed
* customer decision is explicitly `ACCEPTED`
* proposal validity covered the customer decision date
* commercial scope, project, customer reference, delivery lineage, artifact ID, and artifact SHA-256 match
* accepted subtotal, discount, tax, total, currency, payment terms, and revision terms match the proposal
* no prior external-action flags are set
* no conflicting acceptance exists for the same proposal

Eligibility failure returns a structured error and writes no Stage 8K success event.

## Engagement-activation model

`EngagementActivation` is immutable and records the complete source lineage from opportunity through proposal, handoff, presentation, decision, acceptance, delivery record, delivery lineage, artifact ID, artifact SHA-256, customer reference, commercial scope, and accepted commercial terms.

Caller-owned mutable containers are normalized into immutable tuples or copied safe representations before storage.

## Payment/deposit requirement contract

Stage 8K records requirements only. It never processes payment.

Supported payment-start requirements:

* `PAYMENT_NOT_REQUIRED_BEFORE_START`
* `DEPOSIT_REQUIRED_BEFORE_START`
* `FULL_PAYMENT_REQUIRED_BEFORE_START`
* `PAYMENT_REQUIREMENT_UNKNOWN`

Rules enforced:

* payment policy must be explicit
* money uses `Decimal` normalization and repository quantization
* binary floats are rejected by the shared money helper
* required currency must match accepted proposal currency
* required amount must not exceed accepted total
* deposit amount must be greater than zero
* full-payment amount must equal accepted total
* unknown policy blocks readiness
* operator-confirmed payment readiness requires safe evidence, operator ID, date, amount, and currency matching the declared requirement
* no Stage 8A invoice/payment state is mutated

## Customer-input requirement contract

Stage 8K records explicit customer-input requirements. It does not infer completeness.

Supported requirement examples include:

* `FINAL_PRODUCTION_BRIEF`
* `SOURCE_ASSETS`
* `BRAND_GUIDELINES`
* `APPROVAL_CONTACT`
* `PRODUCTION_CONSTRAINTS`
* `OTHER`

Required pending inputs block readiness until an operator records safe local evidence.

## Production schedule contract

Target start and completion dates are optional explicit inputs. When both are supplied, start date must be on or before completion date. No date is inferred.

Dependency and risk notes are explicit bounded text inputs and are included in deterministic activation identity.

## Status machine

Engagement activation statuses:

* `DRAFT`
* `NEEDS_OPERATOR_INPUT`
* `WAITING_FOR_PAYMENT_CONFIRMATION`
* `WAITING_FOR_CUSTOMER_INPUT`
* `READY_FOR_PRODUCTION_REVIEW`
* `APPROVED_FOR_PROJECT_INITIALIZATION`
* `REJECTED`
* `CANCELLED`
* `EXPIRED`

Approval requires a ready activation and an explicit operator decision. Terminal activations cannot be changed except idempotent duplicate approval inspection.

## Deterministic ID design

IDs use existing SCOS canonical JSON and `stable_id` conventions:

* engagement activation ID binds acceptance ID, proposal ID, proposal content hash, and decision ID
* customer-input requirement ID binds activation ID, requirement type, and description
* kickoff authorization ID binds activation ID, engagement content hash, and approval event ID
* informational timestamps are excluded from deterministic activation content identity where required

## Readiness rules

Readiness is read-only. It returns:

* `READY` when explicit payment/deposit and customer-input conditions are satisfied
* `WAITING_FOR_PAYMENT_CONFIRMATION` when deposit/full-payment readiness evidence is pending
* `WAITING_FOR_CUSTOMER_INPUT` when required customer input is pending or blocked
* `NEEDS_OPERATOR_INPUT` when payment policy is unknown or blocked
* `EXPIRED` / `BLOCKED` for terminal or invalid states

Readiness output explicitly keeps project, HVS, render, asset-copy, invoice, payment-link, payment-processing, customer-contact, and automation flags false.

## Kickoff-authorization contract

`ProductionKickoffAuthorization` is created only after `APPROVED_FOR_PROJECT_INITIALIZATION`. It binds:

* engagement activation ID and deterministic content hash
* operator approval event
* complete commercial acceptance lineage
* proposal, delivery, artifact, customer, project, and commercial scope lineage
* accepted total/currency
* payment requirement status
* customer-input status

The authorization states that future project initialization is authorized, but not performed.

## External-action prohibitions

Stage 8K explicitly records:

* HVS project created: NO
* HVS invoked: NO
* render started: NO
* assets copied: NO
* customer contacted: NO
* invoice issued: NO
* payment link created: NO
* payment processed: NO
* automation allowed: NO

## Focused-test totals

Command:

`.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_hvs_engagement_activation_kickoff.py -q -rA --basetemp .stage8k_pytest_temp -o cache_dir=.stage8k_pytest_cache`

Result:

* 18 passed
* 0 failed
* 0 skipped
* exit code 0
* duration: 5.02s

## Regression-test totals

Command:

`.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_stage7_closure_gate.py scos/control_center/tests/test_hvs_delivery_closure.py scos/control_center/tests/test_hvs_delivery_approval.py scos/control_center/tests/test_hvs_customer_receipt_evidence.py scos/control_center/tests/test_hvs_invoice_payment_follow_up.py scos/control_center/tests/test_hvs_delivery_version_lineage.py scos/control_center/tests/test_hvs_revision_rerender_contract.py scos/control_center/tests/test_hvs_rerender_dispatch.py scos/control_center/tests/test_hvs_rerender_result_reconciliation.py scos/control_center/tests/test_hvs_revised_delivery_release_authorization.py scos/control_center/tests/test_hvs_manual_release_receipt_authorization.py scos/control_center/tests/test_hvs_post_delivery_support_authorization.py scos/control_center/tests/test_hvs_revenue_audit_summary.py scos/control_center/tests/test_hvs_customer_outcome_consent_opportunity.py scos/control_center/tests/test_hvs_commercial_proposal_handoff.py scos/control_center/tests/test_hvs_commercial_acceptance_gate.py scos/control_center/tests/test_hvs_engagement_activation_kickoff.py -q -rA --basetemp .stage8k_reg_temp -o cache_dir=.stage8k_reg_cache`

Result:

* 369 passed
* 0 failed
* 0 skipped
* exit code 0
* duration: 63.34s

## Smoke result

Command:

`.venv\Scripts\python.exe scripts\test_smoke.py`

Result:

* 16 passed
* 0 failed
* `SMOKE: PASS`
* exit code 0

## Security result

Command:

`.venv\Scripts\python.exe scripts\security_scan_baseline.py`

Result:

* files scanned: 463
* findings: 0
* `SECURITY SCAN: PASS`
* exit code 0

Focused static searches:

* `rg -n "subprocess|shell=True|os.system" scos/control_center --glob "hvs_engagement_activation*.py"`: no matches
* `rg -n "import hvs|from hvs|python -m hvs|hvs.cli" scos/control_center --glob "hvs_engagement_activation*.py"`: no matches
* `rg -n "requests|urllib|httpx|socket|smtplib|webhook|slack|stripe|payment" scos/control_center --glob "hvs_engagement_activation*.py"`: payment-readiness data-contract fields/messages only; no HTTP/socket/email/Slack/webhook/payment-provider client path

## Collection result

Command:

`.venv\Scripts\python.exe -m pytest --collect-only -q --basetemp .stage8k_collect_temp -o cache_dir=.stage8k_collect_cache`

Result:

* 1,670 tests collected
* 0 collection errors
* exit code 0
* duration: 1.04s

## Full-suite result

Command:

`.venv\Scripts\python.exe -m pytest -q -rA --basetemp .stage8k_full_temp -o cache_dir=.stage8k_full_cache`

Result:

* 1,669 passed
* 1 skipped
* 0 failed
* exit code 0
* duration: 371.56s / 6:11

## Synthetic acceptance evidence

Focused Stage 8K tests used synthetic test-owned runtime storage only.

Covered scenarios:

* valid no-payment-before-start activation through approval and kickoff authorization
* deposit-required activation waiting for payment readiness, then operator-confirmed readiness and authorization
* missing customer input blocking readiness and approval
* invalid commercial lineage rejecting activation without writing Stage 8K success events
* unknown payment policy blocking review and authorization
* CLI lifecycle JSON output and canonical exit codes
* append-only store inspection/evaluation/queue read-only behavior

No synthetic runtime data is committed.

## Known warnings and limitations

* Full suite retains the pre-existing platform skip: `symlink not supported on this platform`.
* A first attempted focused run hit a sandbox temp-permission issue at `C:\Users\chara\AppData\Local\Temp\pytest-of-chara`; all accepted evidence above was rerun with explicit workspace-local pytest temp/cache directories and passed.
* Stage 8K authorizes only future manual Stage 8L initialization. It does not initialize a project.

## HVS unchanged evidence

HVS was inspected read-only before implementation:

* HEAD: `8e054cf368a812a12dec0d179b5374d0612bfdcd`
* branch: `main`
* working tree: clean
* `git diff --check`: passed

Final HVS recheck is required immediately before staging and after commit.

## Runtime artifact hygiene

Generated Stage 8K pytest and diagnostic scratch directories were removed before pre-commit scope review. Runtime JSON/JSONL evidence is gitignored and was not staged.

## Final verdict

PASS - Stage 8K implementation and verification gates passed before local commit.

## Exact proposed commit scope

Expected commit scope:

* `scos/control_center/hvs_engagement_activation_models.py`
* `scos/control_center/hvs_engagement_activation_service.py`
* `scos/control_center/hvs_engagement_activation_store.py`
* `scos/control_center/tests/test_hvs_engagement_activation_kickoff.py`
* `scos/control_center/cli.py`
* `docs/certification/SCOS-HVS-Integration-Stage-8K-engagement-activation-kickoff.md`

## Explicit confirmations

* no HVS project created
* no HVS invocation
* no render
* no asset copy
* no customer contact
* no invoice issued
* no payment link
* no payment processed
* no push
* Stage 8L not started
