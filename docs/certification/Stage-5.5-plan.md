# Stage 5.5 - Operator Packet Review & Manual Handoff Flow

## Stage Goal

Create a local-only operator review layer that lets a human inspect Stage 5.4
prompt/result packets, approve or reject routing, prepare manual handoff
packages, and record decisions without dispatching to real AI apps.

## Scope

- Backend models, review logic, handoff package generation, and JSONL review
  store under `scos/control_center/`.
- Plain executable tests under `scos/control_center/tests/`.
- Contract docs under `docs/specification/`.
- Static Control Center UI mock under `apps/control-center/`.

## Non-goals

No real AI dispatch, clipboard read/write, browser/app/GUI automation,
network/API/cloud calls, database, WebSocket, polling, background worker,
CRM, payment, billing, SaaS, customer portal, commit, push, tag, release,
Stage 4 contract change, Stage 5.1-5.4 public contract break, or
`scos/knowledge` implementation change.

## Files Created

- `scos/control_center/operator_packet_review_models.py`
- `scos/control_center/operator_packet_review.py`
- `scos/control_center/operator_packet_review_store.py`
- `scos/control_center/manual_handoff_package.py`
- `scos/control_center/tests/test_operator_packet_review_models.py`
- `scos/control_center/tests/test_operator_packet_review.py`
- `scos/control_center/tests/test_operator_packet_review_store.py`
- `scos/control_center/tests/test_manual_handoff_package.py`
- `docs/specification/OPERATOR_PACKET_REVIEW_CONTRACT.md`
- `docs/specification/MANUAL_AI_HANDOFF_PACKAGE_CONTRACT.md`
- `apps/control-center/lib/operator-packet-review-types.ts`
- `apps/control-center/lib/operator-packet-review-mock-data.ts`
- `apps/control-center/components/operator-packet-review-panel.tsx`
- `apps/control-center/components/packet-review-card.tsx`
- `apps/control-center/components/manual-handoff-panel.tsx`
- `apps/control-center/components/packet-approval-decision-panel.tsx`

## Files Modified

- `scos/control_center/__init__.py`: additive lazy exports only.
- `apps/control-center/components/app-shell.tsx`: adds Stage 5.5 section.
- `apps/control-center/components/sidebar.tsx`: adds Packet Review nav item.
- `apps/control-center/README.md`: documents Stage 5.5 mock UI.

## Architecture Boundary

Stage 5.5 remains inside the Operator Tools Layer. It consumes Stage 5.4
packet contracts as data, writes only its own review/package/store artifacts,
and does not import or mutate Runtime Product Layer modules. Stage 5.1 command
queue behavior and Stage 5.2-5.4 public contracts remain unchanged.

## Test Commands

Focused Stage 5.5:

```
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_manual_handoff_package.py
```

Stage 5.4 regression:

```
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_builder.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_store.py
```

Stage 5.1-5.3 regression should run all existing control center tests for
command bridge, work sessions, runtime registry, and agent adapters.

Release/safety checks if practical:

```
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
```

Frontend:

```
cd apps/control-center
pnpm lint
pnpm build
```

## Frontend Validation

The Control Center must show a Packet Review navigation item and a Stage 5.5
section with review queue cards, safety-check summaries, local-only decision
buttons, and manual handoff previews. Buttons update React local state only.
There must be no fetch/API route/server action/WebSocket/EventSource/timer/
runtime clock/random/storage/clipboard behavior.

## Static Scan

Confirm the Stage 5.5 backend does not use network, clipboard, browser/app/GUI
automation, subprocess/shell execution, real clock, random, or uuid behavior.
Confirm the frontend contains no forbidden patterns from the task:
`fetch(`, `XMLHttpRequest`, `axios`, `WebSocket`, `EventSource`,
`setInterval`, `setTimeout`, `Date.now`, `Math.random`, `crypto.randomUUID`,
`localStorage`, `sessionStorage`, `navigator.clipboard`, `"use server"`,
`app/api`, `route.ts`, or `middleware.ts`.

## Stage 5.6 Handoff

Recommended next stage: Stage 5.6 - Cross-Agent Workflow Router. It should
consume review decisions and handoff packages as local deterministic records
and still avoid real dispatch until a later explicitly approved integration
contract exists.
