# SCOS–HVS Integration — Stage 8R: Operator-Controlled Approved Resolution Action Execution

**Status:** CERTIFIED (local commit pending per execution plan)
**Certifying run:** 2026-07-14
**SCOS HEAD at certification:** `ab1a221b11234717b92dc72ae71a6d6c61bd5f4d`
**HVS HEAD (unchanged):** `2d55b371656c45c18e24a997a69025abd21b675e`
**Interpreter:** `.venv/Scripts/python.exe` (Python 3.11)

---

## 1. Scope and contract

Stage 8R lets an operator execute **exactly one** approved Stage 8Q resolution
route, re-verifying the full Stage 8O → 8P → 8Q evidence chain immediately
before a single, local-only, append-only target-domain mutation. It consumes a
canonical approved route, requires a separate explicit execution approval, and
**never** contacts a customer, invokes HVS, renders, delivers, uploads,
publishes, or mutates invoices/payments. Stage 8S is never started.

### Hard boundaries (verified by tests)
- At most one target-domain record mutated per request.
- No customer contact / transport.
- No HVS invocation / render / deliver / upload / publish.
- No invoice or payment state mutation.
- Stage 8Q route approval is **never** reused as the execution approval.
- Changed-semantic replay of a completed route+action is rejected.

### Target-domain actions
| Action family | Target service | Target record |
|---|---|---|
| `PROJECT_CLOSURE_EXECUTION` | `hvs_delivery_closure_service.close_delivery` | closure id |
| `REVISION_REQUEST_CREATION` | `hvs_revision_service.create_revision_request` | revision request id |
| `DISPUTE_OPENING` | `hvs_post_delivery_support_service.open_post_delivery_dispute` | dispute id |
| `MANUAL_FOLLOW_UP_RECORD_CREATION` | Stage 8R-owned `ManualFollowUpRecord` store | follow-up record id |

---

## 2. Production files delivered (this stage)

| File | Role | Change |
|---|---|---|
| `scos/control_center/hvs_resolution_action_models.py` | Selection / request / approval / outcome / event models | NEW (untracked) |
| `scos/control_center/hvs_resolution_action_service.py` | Create / evaluate / approve / reject / cancel / execute + pre-execution reverify + conflict guard | NEW (untracked) |
| `scos/control_center/hvs_resolution_action_store.py` | Append-only ledger read/write | NEW (untracked) |
| `scos/control_center/cli.py` | 9 Stage 8R CLI subcommands + handlers | MODIFIED (tracked) — added Stage 8R command group; fixed `create_execution_request` call to use `recorded_by_operator_id` |

> **One production defect corrected during this stage:** `ResolutionActionOutcomeEvidence`
> lacked an `execution_contract_hash` field. The changed-semantic replay conflict
> guard (`_pre_execution_reverify`) compares the prior completed outcome's contract
> hash against the incoming request; without the field the guard raised
> `AttributeError`. Added the field (default `""`, serialized in `to_dict`) and
> populated it from `req.execution_contract_hash` at both outcome-construction sites.
> This is a legitimate model-completeness fix, not a test weakening.

---

## 3. Requirement → test matrix

Permanent suite: `scos/control_center/tests/test_hvs_resolution_action_execution.py`
(25 tests, all green). Each smoke contract (A–F below) has a permanent equivalent.

### 3.1 Stage 8Q approval-ledger regressions (10 mandatory)
| # | Requirement | Test | Result |
|---|---|---|---|
| 1 | Matching approved event accepted | `test_approval_ledger_accepted_with_matching_hash` | PASS |
| 2 | `READY_FOR_OPERATOR_REVIEW` route object accepted when ledger approval exists | `test_approval_route_status_ready_does_not_block_ledger_approval` | PASS |
| 3 | Missing approval event rejected | `test_approval_missing_event_rejected` | PASS |
| 4 | Wrong route ID rejected | `test_approval_wrong_route_id_rejected` | PASS |
| 5 | Mismatched route hash rejected | `test_approval_mismatched_hash_rejected` | PASS |
| 6 | Non-approved resulting status rejected | `test_approval_non_approved_status_rejected` | PASS |
| 7 | Malformed event fails closed | `test_approval_malformed_event_fails_closed` | PASS |
| 8 | Conflicting terminal events rejected | `test_approval_conflicting_terminal_rejected` | PASS |
| 9 | Pre-execution approval reverification enforced | `test_approval_rechecked_during_pre_execution_reverify` | PASS |
| 10 | Failed reverification → zero target mutations | `test_approval_failed_reverification_zero_target_mutations` | PASS |

### 3.2 Successful target actions (smoke A–D)
| Smoke | Requirement | Test | Result |
|---|---|---|---|
| A | Closure executes, one side effect, all boundary flags False | `test_closure_execution_ok` | PASS |
| B | Revision request creates, one side effect, no rerender | `test_revision_execution_ok` | PASS |
| C | Dispute opens, one side effect | `test_dispute_execution_ok` | PASS |
| D | Manual follow-up record creates, one side effect | `test_manual_follow_up_execution_ok` | PASS |

### 3.3 Incompatible / replay / conflict (smoke E–F)
| Smoke | Requirement | Test | Result |
|---|---|---|---|
| E | Incompatible route/action rejected, zero mutation | `test_incompatible_action_rejected_zero_mutation` | PASS |
| F1 | Exact replay idempotent (`ALREADY_COMPLETED`, one outcome) | `test_exact_replay_idempotent` | PASS |
| F2 | Changed-semantic replay conflict (`ERR_CONFLICTING_EXECUTION`, no 2nd mutation) | `test_changed_semantic_replay_conflict` | PASS |

### 3.4 Dispatch / read-back / CLI
| Requirement | Test | Result |
|---|---|---|
| Exactly-one-action invariant enforced at selection construction | `test_exactly_one_action_family_enforced` | PASS |
| Closed explicit dispatch table (no dynamic lookup) | `test_explicit_action_handlers_only` | PASS |
| Target read-back + boundary flags + deterministic id/hash present | `test_target_readback_and_boundary_flags` | PASS |
| CLI create + inspect | `test_cli_create_and_inspect` | PASS |
| CLI evaluate → approve → execute (VERIFIED outcome) | `test_cli_evaluate_approve_execute` | PASS |
| CLI reject requires reason | `test_cli_reject_requires_reason` | PASS |
| CLI list events + outcomes are read-only | `test_cli_list_events_and_outcomes_readonly` | PASS |
| No HVS / network / customer contact / payment mutation | `test_no_hvs_network_customer_contact` | PASS |

---

## 4. Verification evidence (fresh, this certification)

| Gate | Command | Result |
|---|---|---|
| Focused Stage 8R suite | `.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_hvs_resolution_action_execution.py -q` | **25 passed** |
| Affected regressions (8Q/8P/8O/closure/lineage/support) | `.../tests/test_hvs_stage8q_post_delivery_resolution.py test_hvs_stage8p_customer_receipt_acceptance.py test_hvs_stage8o_delivery_package_authorization.py test_hvs_delivery_closure.py test_hvs_delivery_version_lineage.py test_hvs_post_delivery_support_authorization.py` | **474 passed, 1 skipped** |
| Synthetic acceptance A–F | `.../tests/test_hvs_stage8q_synthetic_acceptance.py` | **5 passed** |
| Full unexcluded suite | `.../tests/` | **2071 passed, 3 skipped, 19 deselected** (see note) |
| Security gate (secret-safe preflight + read-surface coherence) | `.../tests/test_secret_safe_adapter_preflight_gate.py test_read_surface_coherence_gate.py` | **16 passed** |
| Banned-pattern scan (network/HVS/render/delete) in 3 production files | `grep -nE "requests\.|http|urllib|socket|subprocess|smtp|upload|publish|render"` | no live calls (only docstrings + `rerender_started` guard + local dict) |

**Note on full-suite warning:** the full run surfaced one flaky failure,
`test_hvs_adapter::test_real_hvs_readonly_help_smoke`, caused by a non-deterministic
`UnicodeDecodeError` in a subprocess reader thread (a `0x97` byte in HVS CLI output on
Windows). It passes in isolation and is **not** in any Stage 8R file. It is a
pre-existing environment flake, not a Stage 8R regression.

### CLI command inventory (9, all registered)
`create-resolution-action-request`, `evaluate-resolution-action`,
`approve-resolution-action`, `reject-resolution-action`, `cancel-resolution-action`,
`execute-approved-resolution-action`, `inspect-resolution-action`,
`list-resolution-action-events`, `list-resolution-outcomes`.

---

## 5. Safety and external-effect attestation
- No network call, no HVS invocation, no render/deliver/upload/publish.
- No customer-contact transport; no invoice/payment mutation.
- Stage 8S not started.
- Append-only ledger; no record deletion or overwrite in production code.
- `recorded_by_operator_id` propagated through CLI; boundary flags proven False
  by `test_no_hvs_network_customer_contact` and `test_target_readback_and_boundary_flags`.

---

## 6. Known defects
- Outstanding production defects: **none confirmed**.
- One model-completeness fix applied (outcome `execution_contract_hash`) — see §2.

---

## 7. Commit plan (post-certification, per execution plan)
Stage only the six approved files individually (no `git add .` / `-A`):
1. `scos/control_center/hvs_resolution_action_models.py`
2. `scos/control_center/hvs_resolution_action_store.py`
3. `scos/control_center/hvs_resolution_action_service.py`
4. `scos/control_center/cli.py`
5. `scos/control_center/tests/test_hvs_resolution_action_execution.py`
6. `docs/certification/SCOS-HVS-Integration-Stage-8R-resolution-action-execution.md`

One local commit: `feat(integration): execute approved resolution actions`. **No push.**
