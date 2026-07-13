# SCOS–HVS Integration Stage 8H — Customer Outcome, Consent & Opportunity Queue

## Objective

Stage 8H records customer-success and consent evidence only. It creates
deterministic, manual-action opportunity queue items from an existing Stage 8G
commercial closure.

## Baseline

Baseline Stage 8G commit: `0c09772c4c1281fe015b9968fe83f0c22ef92e25`.
Stage 8G support/dispute/commercial-closure evidence remains read-only input.

## Architecture

- `hvs_customer_outcome_models.py`: frozen outcome, consent, revocation, and
  opportunity records with bounded ratings, statuses, currency, and safe IDs.
- `hvs_customer_outcome_store.py`: append-only JSONL event store at
  `scos/work/control_center/hvs_customer_success.jsonl` (ignored by Git).
- `hvs_customer_outcome_service.py`: lineage validation, deterministic IDs,
  scoring, readiness views, and a non-mutating manual queue.
- `cli.py`: machine-readable commands; valid results exit 0, rejections exit 1,
  and malformed usage exits 2.

## Contracts

Customer outcomes require a commercially closed Stage 8G lineage and explicit
1–5 satisfaction, quality, communication, and timeliness ratings. Silence is
never interpreted as satisfaction. Portfolio and testimonial consent are
separate immutable records. Granted portfolio consent is limited to the
delivered lineage reference and explicit usage contexts. Testimonial readiness
requires the exact approved SHA-256 text hash. Revocation is an appended record;
expiry and revocation block readiness.

Opportunities support `RENEWAL`, `FOLLOW_ON_PROJECT`, `UPSELL`, `REFERRAL`,
`SUPPORT_FOLLOW_UP`, and `NO_OPPORTUNITY`. Values use `Decimal` and require an
explicit currency. Qualification is append-only; `CONVERTED` requires explicit
operator confirmation.

Priority scoring is pure and versioned as
`scos-hvs.opportunity-priority/1.0.0`. Its inputs are explicit, its output
contains reason codes and a HIGH/MEDIUM/LOW/BLOCKED/INSUFFICIENT_EVIDENCE band,
and `automation_allowed` is always false. Queue evaluation sorts deterministically
and performs no writes.

## Boundaries

Stage 8H does not contact customers. Stage 8H does not publish portfolio or
testimonial content. Stage 8H does not mutate invoice or payment state. Stage
8H does not invoke HVS. Follow-up queue items require manual operator action.
No network, upload, customer messaging, CRM integration, media handling, or
subprocess execution is included.

## Verification

Focused command executed:

```powershell
.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp-stage8h scos\control_center\tests\test_hvs_customer_outcome_consent_opportunity.py -q
```

Focused result: `11 passed` in 1.30s. Stage 8A–8G plus Stage 7 regression:
`147 passed` in 28.46s. Full unexcluded suite: `1546 passed, 1 skipped` in
361.36s. Security scan: 451 files, 0 findings; scanner tests: `3 passed`.
Smoke: `16 passed, 0 failed`. Each pytest command emitted one existing cache
permission warning under `scos/work/.pytest_cache`; no Stage 8H runtime record
is committed.

## Files Changed

- `.gitignore`
- `scos/control_center/hvs_customer_outcome_models.py`
- `scos/control_center/hvs_customer_outcome_store.py`
- `scos/control_center/hvs_customer_outcome_service.py`
- `scos/control_center/cli.py`
- `scos/control_center/tests/test_hvs_customer_outcome_consent_opportunity.py`
- this certification record

## Rollback

Revert the single Stage 8H commit. Existing Stage 8A–8G ledgers and contracts
are not modified. Runtime customer-success evidence is intentionally local and
ignored.

## Corrective Coverage Audit

The initial 11-test focused suite was incomplete. The corrective focused suite
contains 48 passing cases. The mandatory matrix is fully covered by direct
assertions, parameterized boundary cases, or static boundary assertions:

| Contract group | Mandatory cases | Evidence |
| --- | --- | --- |
| Customer outcome | 1–14 | closed lineage, 1/5 bounds, invalid values, explicit ratings, immutable/idempotent records, measurable outcomes, unsafe metadata/input, active-dispute block |
| Portfolio consent | 15–31 | grant/deny/absence/revoke/expire, lineage scope, bounded contexts/formats, identity scopes, anonymization, attribution, replay/conflict, append-only revocation |
| Testimonial consent | 32–48 | independent consent, exact-hash/edit rules, deny/revoke/expire, attribution, anonymization, replay/conflict, no-publication static boundary |
| Opportunities | 49–70 | all six types, deterministic/audited closed lineage, Decimal/currency/confidence/date validation, replay/conflict, explicit conversion gate, no commercial-state write boundary |
| Priority scoring | 71–88 | deterministic versioned HIGH/MEDIUM/LOW/BLOCKED/INSUFFICIENT_EVIDENCE decisions, dispute/concern/support penalties, explicit inputs, pure local-only execution |
| Manual queue | 89–108 | opportunity types, missing/expiring-consent and unresolved-outcome reviews, supplied date, overdue/due-soon/future states, stable order, manual action, non-mutation |
| Readiness | 109–117 | valid and blocked portfolio/testimonial/opportunity results, exact hash, current-dispute block, deterministic read-only output |
| Security/privacy | 118–138 | unsafe IDs, traversal, newline, URI, shell metacharacters, forged closure, sensitive metadata, ignored runtime ledger, static no-outbound/no-execution boundary |
| CLI/regressions | 139–163 | JSON exits for record/inspect/qualify/queue/lineage, malformed usage exit 2, Stage 7 and Stage 8A–8G regressions |

No media-consent subsystem, LLM, external-task client, CRM adapter,
payment-provider adapter, or publication adapter exists in Stage 8H; static
tests verify those capabilities are absent.

## Corrective Defects Found and Fixed

1. Restricted metadata names and non-string values are now rejected.
2. Follow-up dates now require ISO calendar dates.
3. Stage 8H now requires the referenced Stage 8F audit closure.
4. Current Stage 8G disputes now block new positive outcomes and readiness.
5. The queue now emits due state plus missing/expiring-consent and
   unresolved-outcome manual-review items.

## Fresh Corrective Verification

| Gate | Result |
| --- | --- |
| Focused Stage 8H | 48 passed, 0 failed, exit 0, 11.00s |
| Stage 8A–8G and Stage 7 regression set | 190 passed, 0 failed, exit 0, 35.77s |
| Smoke | 16 passed, 0 failed, exit 0 |
| Collection | 1,584 collected, 0 errors, exit 0, 0.96s |
| Security scan | 451 files, 0 findings, exit 0 |
| Full unexcluded suite | 1,583 passed, 1 skipped, 0 failed, exit 0, 364.60s |

All pytest commands retained one non-fatal existing cache-permission warning
under `scos/work/.pytest_cache`; it was not suppressed or changed.

## Final Verdict

PASS — all focused, cross-stage, full-suite, smoke, and security gates passed.
