# Stage 4.17 — First Customer Conversion Handoff / Manual Close Preparation (Plan)

## Stage goal

Add a read-only, local-first, deterministic **manual close preparation** layer over
the Stage 4.16 outcome review. Given a conversion-ready
`first_prospect_outcome_review.json`, generate the exact manual handoff package the
operator needs to confirm scope, offer, pricing, next steps, and close readiness
with a prospect — with human review required before any outreach.

## Scope

- Read a Stage 4.16 outcome review, validate conversion-handoff support, and write a
  deterministic handoff folder + `first_customer_conversion_handoff_manifest.json`.
- Manual preparation only. No payment, money-document generation, money-automation,
  customer-relationship system, `SaaS`, dashboard, portal, auto-DM, message sending,
  network, scraping, or LLM. No mutation of Stage 4.16 (or any 4.1–4.16) artifacts.

## Allowed files

Create:
- `scos/commercial/conversion_handoff_models.py`
- `scos/commercial/first_customer_conversion_handoff.py`
- `scos/commercial/tests/test_first_customer_conversion_handoff.py`
- `docs/specification/FIRST_CUSTOMER_CONVERSION_HANDOFF_CONTRACT.md`
- `docs/certification/Stage-4.17-plan.md`

Modify (lazy exports only, preserving PEP 562 architecture, no eager/knowledge imports):
- `scos/commercial/__init__.py`

## Verification plan

Primary:
```
.venv\Scripts\python.exe scos\commercial\tests\test_first_customer_conversion_handoff.py
```
Expect `RESULT: N passed, 0 failed` (exit 0). Covers: valid ready package;
deterministic + explicit handoff id; all 8 artifacts; manifest references real
paths; deterministic evidence + byte-identical reruns; overwrite semantics; URL
rejection; `INPUT_NOT_FOUND`; `INVALID_OUTCOME_REVIEW` (bad JSON + missing keys);
`CONVERSION_NOT_READY`; `CLOSE_NO_GO` / `BLOCKED` not accepted; sensitive-metadata
rejection; manual-only violation; no source mutation; determinism / `to_dict`;
package-import lazy safety.

Static scan (impl + models source only): confirm absence of network / service /
money / non-determinism tokens (`requests`, `urllib.request`, `http.client`,
`smtplib`, `socket`, `subprocess`, `fetch`, `stripe`, `paypal`, money words,
money-document words, money-automation words, customer-relationship acronym,
`salesforce`, `hubspot`, `sendgrid`, `openai`, `anthropic`, `uuid.uuid4`,
`random.`, `datetime.now`, `date.today`, `time.time`). Boundary marker/exclusion
words are assembled from fragments so the executable source stays token-free.

Import safety:
```
.venv\Scripts\python.exe -c "import sys, scos.commercial as c; assert callable(c.create_first_customer_conversion_handoff); assert not any(m.startswith('scos.knowledge') for m in sys.modules)"
```

## Regression plan

Run (all exit 0):
- `test_first_prospect_outcome_review.py`
- `test_first_prospect_mini_audit_delivery_log.py`
- `test_first_prospect_mini_audit_handoff.py`
- `test_first_prospect_follow_up_decision.py`
- `test_first_prospect_execution_log.py`
- `test_first_outreach_launch_kit.py`
- `scos/knowledge/tests/test_knowledge_service.py`

The Stage 4.17 suite also runs these as embedded regression via subprocess.

## Risks

- **Upstream contract drift**: Stage 4.16 emits `review_id` (not `outcome_review_id`)
  and a nested `action` object. Mitigation: accept both id names and both
  `action`/`next_action` shapes.
- **Static-scan self-flagging**: boundary words in source. Mitigation: assemble all
  marker/exclusion literals from fragments; artifacts (output files) spell them out.
- **Non-determinism**: none introduced — no clock/random/uuid; `checked_at` supplied
  by caller; ids derived via SHA-256; JSON sorted with trailing newline.
- **Accidental mutation**: never writes before validation; only writes inside the
  deterministic `handoff_dir`; never deletes; overwrite touches known filenames only.

## Exit criteria

- Stage 4.17 suite: all pass, 0 failed.
- All regression suites: exit 0.
- Static scan: clean on impl + models.
- Import safety: package import exposes Stage 4.17 lazily without importing knowledge.
- No Stage 4.1–4.16 contract/source changes; no `scos/knowledge` implementation
  changes; no Certified Core changes; no source-artifact mutation.

## No commit / push rule

Implement, test, and report only. **No commit, push, tag, or release.** No
pull/merge/rebase/reset/stash/clean/branch-switch. If unexpected dirty files appear,
stop and report.
