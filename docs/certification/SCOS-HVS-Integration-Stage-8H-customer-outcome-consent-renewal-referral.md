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

## Final Verdict

PASS — all focused, cross-stage, full-suite, smoke, and security gates passed.
