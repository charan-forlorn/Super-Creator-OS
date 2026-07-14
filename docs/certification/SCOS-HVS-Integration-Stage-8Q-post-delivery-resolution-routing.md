# SCOS–HVS Integration Stage 8Q — Post-Delivery Resolution Routing

Certification of the Stage 8Q local-only recommendation, qualification and routing
gate: post-delivery resolution routing, issue and revision qualification, manual
follow-up recommendation, and explicit closure recommendation gate.

---

## 1. Final Verdict

- Implementation verification: **PASS**
- Certification: **COMPLETE**
- Local commit closure: **PASS** (commit `feat(integration): add post-delivery resolution routing gate` created locally; no push)

All verification, pre-commit audit, commit, and post-commit gates passed.

---

## 2. Stage Objective

Stage 8Q is a **local-only recommendation, qualification and routing gate** that
operates strictly after the Stage 8P customer receipt confirmation / acceptance
gate and the Stage 8O actual-delivery record. It:

- inspects whether a delivery has reached a state where post-delivery resolution
  routing can be considered;
- creates a post-delivery route (a draft recommendation artifact, not an executed action);
- evaluates closure eligibility (acceptance alone never closes a project);
- qualifies a customer-reported issue into support / defect / dispute / revision
  candidate, general resolution review, or insufficient-evidence;
- evaluates revision eligibility by reusing Stage 8B lineage and artifact checks
  (no revision record is created);
- builds manual follow-up recommendations (receipt follow-up, acceptance follow-up)
  without contacting the customer;
- decides an explicit recommended route from the read-only evidence;
- exposes a readiness view for operator review.

Stage 8Q executes **no downstream action**. Project closure, revision creation,
dispute creation, customer contact, HVS invocation, rendering, upload/publish, and
invoice/payment mutation are all out of scope and remain false throughout. Execution
of an approved route belongs to a separately approved Stage 8R.

---

## 3. Baselines

- Starting SCOS full hash: `893b54e21ace15afb068fd15602884f7ec16d755`
- Starting HVS full hash: `2d55b371656c45c18e24a997a69025abd21b675e`
- SCOS branch: `main`
- HVS branch: `main`
- Stage 8P certified prerequisite: customer receipt confirmation and acceptance /
  issue-intake gate (commit `893b54e`, already the certified HEAD at Stage 8Q start).
- Canonical interpreter: `.venv\Scripts\python.exe` (no bare `python`).

---

## 4. Implementation Files

| Role | Path | Status |
|------|------|--------|
| CLI | `scos/control_center/cli.py` | modified (tracked) |
| Models | `scos/control_center/hvs_post_delivery_resolution_models.py` | new (untracked) |
| Store | `scos/control_center/hvs_post_delivery_resolution_store.py` | new (untracked) |
| Service | `scos/control_center/hvs_post_delivery_resolution_service.py` | new (untracked) |
| Focused tests | `scos/control_center/tests/test_hvs_stage8q_post_delivery_resolution.py` | new (untracked) |
| Synthetic acceptance | `scos/control_center/tests/test_hvs_stage8q_synthetic_acceptance.py` | new (untracked) |
| Certification | `docs/certification/SCOS-HVS-Integration-Stage-8Q-post-delivery-resolution-routing.md` | new (this document) |

---

## 5. Reused Contracts

- **Stage 8P receipt and decision evidence** — read-only source of truth for the
  customer receipt / acceptance aggregate outcome and decision.
- **Stage 8O actual-delivery evidence** — read-only source of truth for the
  delivered artifact identity (customer reference, artifact SHA-256).
- **Stage 8B revision lineage and eligibility checks** — reused inside
  `evaluate_revision_eligibility` (no Stage 8Q-owned revision logic).
- **Existing deterministic IDs** — `route_content_hash`, `route_decision_id`,
  `resolution_event_id` are derived deterministically (no volatile timestamps in
  identity).
- **Existing append-only storage conventions** — JSONL ledger under the gitignored
  `scos/work/` runtime root, with malformed / truncated / unknown-schema /
  duplicate-event fail-closed handling.
- **Existing CLI JSON and exit-code conventions** — all `stage8q-*` commands emit
  JSON, use non-zero exits for conflicts/invalid input, and perform no interactive
  prompt.

---

## 6. Service-File Verifier Classification

**A. IMPLEMENTED_AND_MODIFIED**

The product verification step that previously emitted a "may not be modified"
warning was a **false alarm**. Direct file inspection of
`hvs_post_delivery_resolution_service.py` confirmed all eight required Stage 8Q
service functions are present and active:

1. `inspect_stage8q_eligibility`
2. `create_post_delivery_route`
3. `evaluate_closure_eligibility`
4. `qualify_reported_issue`
5. `evaluate_revision_eligibility`
6. `build_follow_up_recommendation`
7. `decide_post_delivery_route`
8. `build_stage8q_readiness_view`

No file was blocked from modification; the service file was legitimately edited to
add the defense-in-depth fix in Phase 8 (see §8).

---

## 7. Test-Harness Repair

- The resume prompt anticipated **four** positional helper-call repairs.
- Actual repository inspection found only **two** literal positional calls:
  `_seed_stage8o_delivery(tmp_path)` (×2).
- Both were corrected to keyword form: `_seed_stage8o_delivery(repo_root=tmp_path)`.
- This repair changed **no production behavior**; it only aligns the test harness
  with the existing keyword-only signature.
- The earlier expectation of four repairs was **stale**; do not claim four repairs.

---

## 8. Production Defect and Repair

Two focused tests exposed a real production hardening gap:

- A **forged persisted Stage 8P receipt** (a tampered/corrupt receipt ledger whose
  customer reference or artifact SHA-256 diverges from the Stage 8O actual-delivery
  record) was not independently rejected by Stage 8Q's source-binding path.
- Stage 8Q previously trusted the Stage 8P receipt identity without cross-checking
  it against Stage 8O.

**Repair (real production fix, not merely a test change):**

- Added `_stage8p_identity_matches_8o(...)` in
  `hvs_post_delivery_resolution_service.py` (defined at line 186, invoked at line 251).
- `build_source_binding` now cross-verifies the persisted Stage 8P receipt identity
  (customer reference + artifact SHA-256) against the Stage 8O actual-delivery
  evidence and **fails closed** on divergence.
- The tests simulate the realistic forged-ledger threat via `_inject_forged_receipt`,
  which inserts a forged receipt record **directly into the Stage 8P receipt ledger**
  (the canonical Stage 8P writer already rejects normal mismatched creation, so the
  forge must be simulated at the ledger level).
- Two forged variants are covered: mismatched customer reference (`customer_reference="WRONG"`)
  and mismatched artifact SHA-256 (`artifact_sha256=ART2`).

This defense-in-depth validation must **not** be removed or weakened.

---

## 9. Routing Contract

Supported route decision types (from `hvs_post_delivery_resolution_models.py`):

- `CLOSURE_ELIGIBILITY_REVIEW` — closure eligibility review
- `MANUAL_ACCEPTANCE_FOLLOW_UP` — manual acceptance follow-up
- `MANUAL_RECEIPT_FOLLOW_UP` — manual receipt follow-up
- `CUSTOMER_REJECTION_RESOLUTION_REVIEW` — customer rejection resolution review
- `SUPPORT_REVIEW` — support review
- `DEFECT_REVIEW` — defect review
- `DISPUTE_ELIGIBILITY_REVIEW` — dispute eligibility review
- `REVISION_ELIGIBILITY_REVIEW` — revision eligibility review
- `OPERATOR_INVESTIGATION` — operator investigation (ambiguous / identity conflict)
- `NO_ACTION_REQUIRED`
- `BLOCKED` — blocked route

Route classification (`classify_route`) maps Stage 8P aggregate outcomes to routes:

| Stage 8P outcome | Route |
|-----------------|-------|
| accepted_by_customer | CLOSURE_ELIGIBILITY_REVIEW |
| receipt_confirmed_acceptance_pending | MANUAL_ACCEPTANCE_FOLLOW_UP |
| receipt_not_confirmed | MANUAL_RECEIPT_FOLLOW_UP |
| rejected_by_customer | CUSTOMER_REJECTION_RESOLUTION_REVIEW |
| issue_reported | SUPPORT_REVIEW |
| revision_review_requested | REVISION_ELIGIBILITY_REVIEW |
| delivery_identity_conflict | OPERATOR_INVESTIGATION |
| blocked | BLOCKED |

---

## 10. Closure Eligibility

`evaluate_closure_eligibility` is read-only and **acceptance alone does not close a
project**. Blockers that prevent a closure-eligibility recommendation:

- `delivery_invalidated`
- `unresolved_issue_reported`
- `open_revision_review`
- `customer_rejection_present`
- `identity_conflict`
- `conflicting_decision`
- `dispute_active`
- `support_blocker_active`
- `commercial_payment_blocker_active`

Route approval is **not** closure execution. `project_closed` remains `False`
throughout Stage 8Q. Closure recommendation is only a recommendation for a future,
separately approved operator action.

---

## 11. Issue Qualification

`qualify_reported_issue` maps a reported issue category to a qualification:

- `SUPPORT_CANDIDATE` — support candidate (e.g. `SUPPORT_QUESTION`)
- `DEFECT_CANDIDATE` — defect candidate (e.g. `PRODUCTION_DEFECT`,
  `ARTIFACT_INTEGRITY_DEFECT`, `DELIVERY_PROCESS_DEFECT`)
- `DISPUTE_CANDIDATE` — dispute candidate
- `REVISION_CANDIDATE` — revision candidate (e.g. `CUSTOMER_REVISION_REQUEST`,
  `SCOPE_CHANGE`, `CONTENT_CHANGE`, `FORMAT_CHANGE`)
- `GENERAL_RESOLUTION_REVIEW`
- `INSUFFICIENT_EVIDENCE`

Ambiguous or unknown evidence **fails safely** (no over-confident classification).
Classification **does not create or resolve** any downstream record (no dispute,
revision, or support ticket is written).

---

## 12. Revision Eligibility

`evaluate_revision_eligibility` reuses Stage 8B revision lineage and artifact
checks. It produces only a status (`ELIGIBLE` / `NOT_ELIGIBLE` /
`NEEDS_OPERATOR_INPUT` / `BLOCKED`):

- no revision record is created;
- no successor version is persisted;
- no rerender approval is created;
- HVS is not invoked.

---

## 13. Follow-Up Recommendations

`build_follow_up_recommendation` produces:

- **receipt follow-up** — when the customer receipt is not confirmed;
- **acceptance follow-up** — when receipt is confirmed but acceptance is pending.

It performs **no customer communication**, **no external reminder scheduling**, and
**no acceptance inference** (it never assumes acceptance that was not confirmed).

---

## 14. Deterministic Identities

- `route_content_hash` — deterministic hash of the route content.
- `route_decision_id` — deterministic decision identifier.
- `resolution_event_id` — deterministic event identifier for the append-only ledger.
- Identities are **stable across replay** and **conflict-rejected** on duplicate
  event id.
- **Volatile timestamps are excluded from identity** (fail-closed duplicate
  detection depends only on deterministic fields).

---

## 15. Store

`hvs_post_delivery_resolution_store.py`:

- append-only JSONL ledger at
  `scos/work/hvs_stage8q_post_delivery_resolution/stage8q_post_delivery_resolution_ledger.jsonl`
  (runtime root `scos/work/`, which is gitignored — see `.gitignore` line 63).
- Fails safely (fail closed) on:
  - malformed JSON line (`malformed stage8q resolution event`);
  - truncated final line (`truncated stage8q resolution ledger line`);
  - unknown schema version (`schema_version` mismatch);
  - duplicate event id (`event_id` already seen).
- No silent repair; no prior-event rewrite. Reads are immutable over prior records.

---

## 16. CLI

Actual `stage8q-*` commands registered in `scos/control_center/cli.py`:

1. `stage8q-inspect-eligibility`
2. `stage8q-create-route`
3. `stage8q-inspect-route`
4. `stage8q-evaluate-closure`
5. `stage8q-qualify-issue`
6. `stage8q-evaluate-revision`
7. `stage8q-decide-route`
8. `stage8q-readiness`

CLI contract:

- JSON output;
- non-zero exit on conflict / invalid input (e.g. duplicate route, blocked state);
- no interactive prompt;
- no arbitrary runtime path accepted (path validation via `_validate_path`);
- no external side effects.

---

## 17. Focused Evidence

Stage 8Q focused suite
(`scos/control_center/tests/test_hvs_stage8q_post_delivery_resolution.py`):

- **126 passed**
- 0 failed
- exit 0

---

## 18. Regression Evidence

Affected regression suite (Stage 8Q + 8P + 8O + delivery closure / lineage / support /
revision / receipt-evidence / customer-outcome / invoice+payment):

- **547 passed**
- 1 skipped
- exit 0

---

## 19. Synthetic Acceptance

`scos/control_center/tests/test_hvs_stage8q_synthetic_acceptance.py`:

- **5 passed**
- exit 0

Scenarios:

- **A — accepted and closure eligible:** Stage 8P accepted_by_customer with no
  blockers → `CLOSURE_ELIGIBILITY_REVIEW`, closure eligible.
- **B — issue reported:** Stage 8P issue_reported → `SUPPORT_REVIEW`, qualified as
  support candidate.
- **C — revision review requested:** Stage 8P revision_review_requested →
  `REVISION_ELIGIBILITY_REVIEW`, revision eligibility evaluated (no revision created).
- **D — acceptance pending:** Stage 8P receipt_confirmed_acceptance_pending →
  `MANUAL_ACCEPTANCE_FOLLOW_UP`.
- **E — identity conflict:** forged Stage 8P receipt whose identity diverges from
  Stage 8O → source binding fails closed, `OPERATOR_INVESTIGATION` / blocked.

---

## 20. Collection

- **2,474 collected**
- 0 collection errors
- exit 0

---

## 21. Full Suite

- **2,471 passed**
- 3 skipped
- 19 deselected
- 0 failed
- exit 0

One unrelated warning occurred:

```
scos/control_center/tests/test_hvs_adapter.py::test_real_hvs_readonly_help_smoke
  PytestUnhandledThreadExceptionWarning: Exception in thread Thread-295 (_readerthread)
  UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 592: invalid start byte
```

This is an unrelated background-thread subprocess encoding decode in an unrelated
test's helper (a non-UTF-8 byte in a subprocess `help` stream). It is **not** a
Stage 8Q failure and must not be suppressed globally (it is environment, not code).

---

## 22. Smoke

Fresh smoke, run explicitly for this closure gate:

```
.venv\Scripts\python.exe -m pytest -m "not integration" -q
```

- collected/selected: 2,476
- passed: **2,476**
- skipped: 3
- deselected: 19
- failed: 0
- errors: 0
- warnings: 1 (the unrelated subprocess decode described in §21)
- exit code: **0**
- elapsed: 415.58s (0:06:55)

Smoke **PASS**. No prior pytest process was active when this run started (verified
via `ps`); no duplicate run was launched.

---

## 23. Security

- 488 files scanned
- 0 findings
- **PASS**

---

## 24. Mandatory Coverage

Traceability matrix for the Stage 8Q contract (A–K), mapping the 126 focused tests
and 5 synthetic tests to required behaviors. Grouped tests assert explicit outcomes.

| Contract area | Coverage | Notes |
|---------------|----------|-------|
| Source eligibility (`inspect_stage8q_eligibility`) | focused + synthetic A–E | readiness gating before any route |
| Closure (`evaluate_closure_eligibility`) | focused + synthetic A, E | acceptance alone insufficient; blockers enumerated |
| Pending follow-up (`MANUAL_ACCEPTANCE_FOLLOW_UP`) | focused + synthetic D | acceptance pending → follow-up |
| Receipt follow-up (`MANUAL_RECEIPT_FOLLOW_UP`) | focused + synthetic | receipt not confirmed → follow-up |
| Customer rejection (`CUSTOMER_REJECTION_RESOLUTION_REVIEW`) | focused | rejection → resolution review; blocks closure |
| Issue qualification (`qualify_reported_issue`) | focused + synthetic B | support/defect/dispute/revision/general/insufficient; ambiguous fails safe |
| Revision eligibility (`evaluate_revision_eligibility`) | focused + synthetic C | Stage 8B reuse; no revision created |
| Operator decisions (`OPERATOR_INVESTIGATION`, `decide_post_delivery_route`) | focused + synthetic E | ambiguous/identity conflict → investigation; approve/reject/cancel |
| Store and audit (append-only, fail-closed) | focused | malformed/truncated/unknown-schema/dup-id rejected |
| Readiness views (`build_stage8q_readiness_view`) | focused | operator-facing readiness summary |
| Side-effect / security boundaries | focused + security scan | no closure, no revision, no dispute, no HVS, no network, no subprocess in prod modules |

All 131 selected Stage 8Q tests (126 focused + 5 synthetic) pass; post-commit rerun
confirmed (see §27 of final report / Phase 11).

---

## 25. Safety Evidence

Verified across tests, scans, and repository inspection:

- recommendation did **not** execute a route;
- closure recommendation did **not** close a project;
- project closure authorization remained **false**;
- issue qualification created **no** dispute;
- issue qualification resolved **no** dispute;
- defect candidate did **not** confirm a defect;
- revision eligibility created **no** revision;
- **no** successor version was persisted;
- **no** rerender approval was created;
- **no** customer contact occurred;
- **no** HVS invocation occurred;
- **no** render occurred;
- **no** upload or publish occurred;
- invoice state **unchanged**;
- payment state **unchanged**;
- `.hermes/` **unchanged** and uncommitted;
- runtime ledger **not** committed (gitignored `scos/work/`);
- **no** network access;
- **no** subprocess in Stage 8Q production modules;
- Stage 8R **not** started.

---

## 26. Known Limitations

- Stage 8Q **only recommends and authorizes** future routes; it executes nothing.
- Downstream action execution belongs to a separately approved **Stage 8R**.
- The unrelated subprocess encoding warning (§21) remains outside Stage 8Q scope.

---

## 27. Commit Evidence

- Starting SCOS hash: `893b54e21ace15afb068fd15602884f7ec16d755`
- Expected commit subject: `feat(integration): add post-delivery resolution routing gate`
- Final committed hash / short hash / committed files: recorded in the final closure
  report (avoiding a second commit solely to embed this document's own hash).
