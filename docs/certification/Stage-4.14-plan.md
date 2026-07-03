# Stage 4.14 — First Prospect Mini-Audit Handoff Package (Certification Plan)

## Scope

Add a local-only generator that turns an eligible Stage 4.13 follow-up decision into a
deterministic mini-audit handoff folder for manual operator review. Eligible decisions are
`SEND_MINI_AUDIT` (always) and `ESCALATE_TO_FIRST_CUSTOMER_FLOW` (only with explicit
opt-in). The generator writes local files only; the operator reviews and sends outside SCOS.

Deliverables:
- `scos/commercial/mini_audit_handoff_models.py` — immutable models + constants.
- `scos/commercial/first_prospect_mini_audit_handoff.py` —
  `create_first_prospect_mini_audit_handoff`.
- `scos/commercial/tests/test_first_prospect_mini_audit_handoff.py` — plain-script suite.
- `docs/specification/FIRST_PROSPECT_MINI_AUDIT_HANDOFF_CONTRACT.md` — the contract.
- `scos/commercial/__init__.py` — lazy exports only (no eager imports, no knowledge import).

## Assumptions

- The Stage 4.13 decision artifact is the primary input; the referenced Stage 4.12
  execution log supplies safe prospect context. Both are read-only; their actual (verified)
  shapes are authoritative and unchanged by Stage 4.14.
- `checked_at` is always supplied explicitly by the caller (no clock is read).
- A missing referenced execution log degrades to a recorded blocker + `accepted=False`
  (package still generated with reduced context), not a hard failure.

## Architecture boundary

- Read-only over Stage 4.12 / 4.13; never mutates any source artifact or Stage 4.1–4.13
  contract.
- Stdlib only + Stage 4.1 `FrozenMap`. Allowed imports: `pathlib`, `json`, `hashlib`,
  `re`, `typing`, `dataclasses`, `FrozenMap`, `mini_audit_handoff_models`.
- No import of KnowledgeService / lower knowledge engines / Stage 4 report or delivery
  builders / outreach-sending utilities / network / cloud / billing libraries.

## No-SaaS / no-network / no-LLM rules

- No network, cloud, SaaS, or permission-server calls. `http(s)://` paths rejected.
- No LLM usage; artifact content is deterministic templating, not generation.
- Deterministic outputs only — no real clock, random, uuid, or environment-dependent data.

## No-CRM / no-scraping / no-auto-DM / no-billing rules

- No CRM, no lead scraping/enrichment, no auto-DM, no email/LINE automation, no message
  sending, no billing, no dashboard, no customer portal, no automatic outreach.
- A detected non-manual/automation signal inside an inspected artifact fails with
  `MANUAL_ONLY_VIOLATION`; the package is never built.
- `handoff_message_draft.md` is a manual draft with an explicit review banner and no
  guarantees / auto-send / PII / platform instruction.
- A static forbidden-token scan (executable source only) guards against network / vendor /
  scraping / CRM / auto-message / knowledge-engine / billing / `auth` tokens.

## No real customer PII

Direct personal-data keys (`phone, email, address, personal_name, personal_id, national_id,
tax_id`) anywhere in the decision, the execution-log prospect metadata, or mini-audit
metadata are rejected with `SENSITIVE_METADATA`. Generic business display aliases allowed.
`prospect_context.json` carries safe fields only.

## Required test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_mini_audit_handoff.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_follow_up_decision.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_execution_log.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_outreach_launch_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_operator_practice_lab.py
.venv\Scripts\python.exe scos\commercial\tests\test_launch_certification_pack.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_paid_customer_dry_run.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
```

## Remaining risks

- Stage 4.13's decision shape and Stage 4.12's execution-log shape are hard dependencies;
  a future upstream rename would require updating Stage 4.14's normalization (and this
  doc), never the reverse.
- Automation-signal and PII detection are key-name based; deliberately obfuscated signals
  are out of scope (the manual-only guardrail is an operator aid, not an adversarial filter).
- The generated draft is intentionally generic; operators must localize and verify claims
  before sending.

## PASS criteria

- All 15 required suites pass with 0 failures (Stage 4.14 suite is 78 checks, 0 failures).
- No Certified Core, `scos/knowledge` implementation, or Stage 4.1–4.13 contract changes.
- The source decision artifact and execution log are byte-for-byte unchanged after a run.
- The executable source contains none of the forbidden tokens.

## Note

Stage 4.14 is a **manual handoff package generator only**. It reads an eligible Stage 4.13
decision (and the Stage 4.12 log it references), generates a deterministic local
handoff folder for manual review, and alters no Stage 4.1–4.13 contract. It performs no
CRM / scraping / auto-DM / billing / SaaS / dashboard / customer-portal / network / LLM
behavior and never sends anything.
