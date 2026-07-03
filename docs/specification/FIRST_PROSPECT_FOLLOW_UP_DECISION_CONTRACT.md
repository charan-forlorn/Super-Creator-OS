# First Prospect Follow-up Decision Contract (Stage 4.13)

## Purpose

Stage 4.13 is a **read-only decision gate**. Given the evidence in a Stage 4.12
`prospect_execution_log.json`, it deterministically decides what the operator should
**manually** do next. It answers exactly one question:

> "Given the first-prospect execution evidence, what should the operator manually do next?"

It is a decision layer only. It never sends messages, never contacts external services,
never keeps a customer database, never touches billing, and never mutates the source log.

## Architecture

```
prospect_execution_log.json  (Stage 4.12 output, read-only)
        │
        ▼
decide_first_prospect_follow_up()
        │  validate → normalize → evaluate → decide
        ▼
FirstProspectFollowUpDecisionResult | FirstProspectFollowUpDecisionError
        │  (optional)
        ▼
first_prospect_follow_up_decision.json
```

Stage 4.13 may **read** Stage 4.12 output files. It must **not** call outreach, CRM,
message-sending, scraping, billing, network, or SaaS functions, and must not modify any
Stage 4.12 artifact. It uses only the Python standard library plus the Stage 4.1
`FrozenMap`. It never uses the real clock, random, uuid, network, or environment-dependent
values — every output is a pure function of its inputs.

## Public API

```python
from scos.commercial.first_prospect_follow_up_decision import decide_first_prospect_follow_up

decide_first_prospect_follow_up(
    *,
    execution_log_path,            # str | pathlib.Path — Stage 4.12 log file
    checked_at: str,               # explicit caller-supplied timestamp string
    output_path=None,              # str | pathlib.Path | None
    require_human_review: bool = True,
    allow_escalation: bool = False,
) -> FirstProspectFollowUpDecisionResult | FirstProspectFollowUpDecisionError
```

- `execution_log_path` must exist and be a file. `http://` / `https://` paths are rejected.
- `checked_at` must be a non-empty string (no real clock is ever read).
- `output_path` is optional. When given, the decision report is written only after all
  validation passes. If it ends with `.json` it is treated as the target file; otherwise
  it is treated as a directory and `first_prospect_follow_up_decision.json` is written inside.
- The function never deletes files and never modifies the inspected source log.

## Model contracts

All models are immutable (`@dataclass(frozen=True)`), reuse the Stage 4.1 `FrozenMap`, and
serialize via `to_dict()` with explicit key order (tuples → lists, nested dataclasses via
their own `to_dict()`, `FrozenMap` → plain dict). Callers write JSON with
`sort_keys=True, indent=2` plus a trailing newline.

`FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION = 1`

**FollowUpDecisionCheck** — `check_name, status, severity, artifact_path, error_kind,
error_detail, metadata`. `status ∈ {success, failure, skipped}`,
`severity ∈ {info, warning, error}` (validated in `__post_init__`).

**FollowUpDecisionAction** — `action, reason, priority, due_at, requires_human_review,
metadata`. `action ∈ FOLLOW_UP_ACTIONS`, `priority ∈ {low, normal, high, urgent}`.

**FirstProspectFollowUpDecisionResult** — `ok, schema_version, accepted, decision_id,
execution_log_id, prospect_id, checked_at, action, source_execution_log_path, output_path,
checks, blockers, metadata`.

**FirstProspectFollowUpDecisionError** — `ok, schema_version, error_kind, error_detail,
failed_check, checks, blockers, metadata`.

## Input execution-log assumptions & normalization

Stage 4.13 aligns to the **actual** Stage 4.12 output (it never changes Stage 4.12).
The Stage 4.12 log nests fields, so Stage 4.13 normalizes as follows:

| Stage 4.13 concept | Actual Stage 4.12 location |
| --- | --- |
| prospect id | `prospect.prospect_id` |
| response status | `response_status.status` |
| next action | `response_status.next_action` |
| follow-up due | `response_status.follow_up_due` |
| blockers (list) | derived from `response_status.blocker_summary` (0 or 1 element) |
| checked-at | top-level `checked_at` **or** `created_at` |

Required top-level keys: `schema_version`, `execution_log_id`, `prospect` (with
`prospect_id`), `response_status` (with `status`), `outreach_action`,
`outreach_launch_kit_path`, `metadata`, and one of `checked_at` / `created_at`.

## Response-status normalization → decision action

| Stage 4.12 status | Decision action |
| --- | --- |
| `interested` | `SEND_MINI_AUDIT` (or `ESCALATE_TO_FIRST_CUSTOMER_FLOW` if `allow_escalation=True`) |
| `mini_audit_requested` | `SEND_MINI_AUDIT` (or escalation, same rule) |
| `contacted` | `FOLLOW_UP` if a follow-up is due / next action mentions follow-up, else `WAIT` |
| `no_response` | `FOLLOW_UP` if a follow-up is due / next action mentions follow-up, else `WAIT` |
| `follow_up_needed` | `FOLLOW_UP` |
| `not_interested` | `CLOSE_NO_GO` |
| `blocked` | `BLOCKED` |
| `not_contacted` | `WAIT` |
| unknown | `INVALID_RESPONSE_STATUS` error |

## Decision-action model

`FOLLOW_UP_ACTIONS = (FOLLOW_UP, SEND_MINI_AUDIT, WAIT, CLOSE_NO_GO,
ESCALATE_TO_FIRST_CUSTOMER_FLOW, BLOCKED)`.

**`ESCALATE_TO_FIRST_CUSTOMER_FLOW` is a manual operator recommendation label only.** The
function does not create customer records, packages, outreach, CRM entries, or call any
Stage 4.6 / 4.8 flow. It is a string in the decision, nothing more.

## Decision rules

- `accepted = True` when a usable action was produced
  (`FOLLOW_UP`, `SEND_MINI_AUDIT`, `WAIT`, `CLOSE_NO_GO`, `ESCALATE_TO_FIRST_CUSTOMER_FLOW`).
- `accepted = False` when the log was inspected but must not be acted on yet (`BLOCKED`,
  from a recorded blocker, a `blocked` status, or a detected non-manual signal).
- A detected non-manual / automation signal (an `auto_send`, `auto_dm`, `crm_sync`,
  `scrape*`, billing, `saas`, or `network` key set truthy anywhere in the log) is **never**
  a hard error — the log was successfully inspected. It yields a `BLOCKED` result with
  `priority=urgent`, `requires_human_review=True`, and the signal recorded in `blockers`.
- Escalation always keeps `requires_human_review=True`.
- Blocker priority is `high`, or `urgent` when the blocker summary mentions "high" or
  "critical".

## Output schema — `first_prospect_follow_up_decision.json`

Deterministic UTF-8 / LF JSON, `sort_keys=True`, `indent=2`, trailing newline. Content is
`FirstProspectFollowUpDecisionResult.to_dict()`:

```json
{
  "accepted": true,
  "action": {
    "action": "SEND_MINI_AUDIT",
    "due_at": null,
    "metadata": {"source_status": "interested"},
    "priority": "high",
    "reason": "Prospect shows strong interest; prepare and send a manual mini-audit.",
    "requires_human_review": true
  },
  "blockers": [],
  "checked_at": "2026-07-03T07:00:00Z",
  "checks": [ {"check_name": "validate_inputs", "...": "..."} ],
  "decision_id": "follow-up-decision-prospect-001-2026-07-03t07-00-00z-<sha256[:12]>",
  "execution_log_id": "prospect-execution-...",
  "metadata": {"decider": "scos.commercial.first_prospect_follow_up_decision",
               "manual_only": true, "manual_only_violation": false},
  "ok": true,
  "output_path": "…/first_prospect_follow_up_decision.json",
  "prospect_id": "prospect-001",
  "schema_version": 1,
  "source_execution_log_path": "…/prospect_execution_log.json"
}
```

`decision_id` is derived deterministically from `execution_log_id | prospect_id |
checked_at | action` (sanitized text + a SHA-256 12-char prefix). No uuid, random, or clock.

## Error kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `INVALID_EXECUTION_LOG`, `INVALID_RESPONSE_STATUS`,
`SENSITIVE_METADATA`, `PATH_CONTAINMENT_FAILED`, `OUTPUT_WRITE_FAILED`.

A hard `Error` is returned **only** for cases that prevent inspection: missing/URL path,
unreadable JSON, missing required contract fields, an unrecognized response status, a
direct personal-data field, an unsafe output path, or an output write failure. A detected
non-manual signal is **not** a hard error (see decision rules).

## Determinism guarantees

- Output is a pure function of `(execution_log_path contents, checked_at, output_path,
  require_human_review, allow_escalation)`.
- No real clock, random, uuid, network, or environment-dependent output.
- Repeated runs with identical inputs produce byte-identical JSON.

## Boundary rules (local-only, manual-only)

- **Local-only:** filesystem paths only; `http://` / `https://` rejected; no network,
  cloud, or SaaS calls.
- **Manual-only:** the gate recommends manual operator actions; it never performs them.
- **No real customer PII:** direct personal-data keys (`phone`, `email`, `address`,
  `personal_name`, `personal_id`, `national_id`, `tax_id`) are rejected. Generic business
  display aliases (e.g. `display_name`, `display_alias`) are allowed.
- **No CRM / scraping / auto-DM / message-sending / billing / SaaS / dashboard / network /
  LLM** behavior of any kind. No customer portal. Not an LLM evaluator.
- Does not alter any Stage 4.1–4.12 contract and never mutates the source log.

## Examples

```python
# Strong interest, no escalation → send a manual mini-audit.
decide_first_prospect_follow_up(execution_log_path="out/prospect_execution_log.json",
                                checked_at="2026-07-03T07:00:00Z")

# Same evidence, escalation permitted → recommend the first-customer path (label only).
decide_first_prospect_follow_up(execution_log_path="out/prospect_execution_log.json",
                                checked_at="2026-07-03T07:00:00Z", allow_escalation=True)

# Persist the decision next to the log.
decide_first_prospect_follow_up(execution_log_path="out/prospect_execution_log.json",
                                checked_at="2026-07-03T07:00:00Z",
                                output_path="out/first_prospect_follow_up_decision.json")
```

## Out of scope

CRM, lead scraping/enrichment, auto-DM, email/LINE automation, message sending, billing,
SaaS, dashboards, customer portals, LLM evaluation, network/cloud access, and any mutation
of Stage 4.1–4.12 artifacts. Stage 4.13 is a manual decision gate only.
