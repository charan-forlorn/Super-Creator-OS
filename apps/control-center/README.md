# SCOS Agent Control Center - v0.1.2 (Frontend Prototype)

A dark-mode dashboard for a solo operator coordinating the four SCOS agents
during stage-gated development:

| Agent | Role |
| --- | --- |
| ChatGPT | Orchestrator |
| Claude Code | Builder |
| Codex | Reviewer / Verifier |
| Hermes | Repo Health / Workflow Auditor |

The interface is designed to answer, at a glance:

1. What should I do next?
2. Which agent owns the next step?
3. Is the latest result PASS, FAIL, BLOCKED, or NEEDS REVIEW?
4. What prompt should I copy next?
5. What result should I paste or review?
6. Is this ready to merge, or does it need a fix?

## v0.1.2 - Operator Workflow Clarity

v0.1.2 adds manual workflow guidance without adding integration behavior:

- Next Action panel: immediate operator action, owning agent, source item,
  urgency, reason, and disabled visual affordances.
- Handoff strip: static workflow chain from ChatGPT to Claude Code to Codex to
  Hermes to Merge Decision.
- Result routing: each Result Inbox item explains whether it routes to Merge
  Queue, Request Fix, Preflight / Operator action, or review.
- Decision Guidance: each Merge Queue item shows the recommended decision,
  evidence requirement, reason, and risk level.
- Manual copy flow: Prompt Builder and Result Inbox explain the manual prompt
  and result handoff path.
- Operator checklist: Task Detail separates task checklist progress from manual
  operator gate readiness.

This is a frontend prototype only. It is 100% local-first: static mock data,
React local state, and a CSS-only animated mascot ("Orbit"). There is no backend,
database, API route, network request, auth, clipboard integration, storage, form
submission, or real agent dispatch behavior. All action-looking workflow buttons
are disabled/inert.

## Stage 5.1 - Command Bridge Mock

The "Command Bridge (Stage 5.1)" section previews the local command bridge
implemented in `scos/control_center/` with static deterministic mock data only:

- Command Draft panel: a validated draft and a rejected (unknown command type)
  draft, with validation status and errors.
- Operator Approval panel: one approved and one rejected decision, showing the
  no-auto-approval rule and deterministic approval ids.
- Command Event Log: the append-only JSONL lifecycle
  (DRAFTED → VALIDATED → APPROVED → QUEUED → STARTED → COMPLETED, plus a
  REJECTED example).

Types live in `lib/command-types.ts`, data in `lib/command-mock-data.ts`. The
UI never executes commands — real execution happens only in the Python bridge
behind the operator approval gate.

## Stage 5.3 - AI Agent Adapter Contract Layer Mock

The "AI Agent Adapters (Stage 5.3)" section previews the adapter contract
layer implemented in `scos/control_center/agent_adapter_*.py` with static
deterministic mock data only:

- Agent Adapter panel: one card per adapter (ChatGPT, Claude Code, Codex,
  Hermes, manual clipboard fallback) showing declared runtime types,
  supported task types, and the three capability flags (prompt delivery,
  result capture, status check), plus a distinct "always-on fallback" badge
  for manual clipboard.
- Adapter Simulation panel: one fixed simulated lifecycle (request_created →
  request_validated → adapter_selected → prompt_prepared → simulated_sent →
  result_simulated → result_ready) and a note that real dispatch is
  disabled, with a handoff pointer to Stage 5.4 — Unified Prompt & Result
  Packet.

Types live in `lib/agent-adapter-types.ts`, data in
`lib/agent-adapter-mock-data.ts`. No adapter here calls an API, opens an
app, drives a browser, or automates a clipboard — every card and lifecycle
step is static, deterministic display data.

## Stage 5.4 - Unified Prompt & Result Packet Mock

The "Unified Prompt & Result Packets (Stage 5.4)" section previews the
packet contract layer implemented in
`scos/control_center/prompt_result_packet_*.py` with static deterministic
mock data only:

- 6 prompt/result scenario cards: ChatGPT planning → Claude Code
  implementation, Claude Code implementation → Codex review, Codex
  needs-fix → back to Claude Code, Codex pass → Hermes audit, Hermes audit
  → ChatGPT status update, and one BLOCKED result escalated to the
  operator.
- Each card shows the prompt packet (source/target agent, objective,
  context refs, status), the result packet (verdict, summary, artifacts,
  blockers, recommended next agent), and the routing recommendation (next
  agent, next packet type, whether operator approval is required).
- Packet Routing Flow: the named 5-stage chain (ChatGPT → Claude Code →
  Codex → Hermes → ChatGPT), each stage showing its packet type and result
  verdict.

Types live in `lib/prompt-result-packet-types.ts`, data in
`lib/prompt-result-packet-mock-data.ts`. No packet here is sent anywhere and
no routing decision is executed — every card and flow stage is static,
deterministic display data.

## Stage 5.5 - Operator Packet Review Mock

The "Packet Review" section previews the operator packet review and manual
handoff layer implemented in `scos/control_center/operator_packet_review*.py`
and `manual_handoff_package.py` with static deterministic mock data only:

- Review queue: ChatGPT -> Claude Code approval, Claude Code -> Codex review,
  Codex NEEDS_FIX -> Claude Code manual handoff, Hermes BLOCKED -> operator,
  one rejected route, and one approved handoff preview.
- Packet review cards show source/target agent, runtime, routing reason,
  safety-check summary, blocked/warning state, and required operator decision.
- Manual handoff panel shows target runtime, prompt preview, context preview,
  deterministic steps, and an inert "copy manually outside SCOS" note.
- Decision buttons update React local state only. They do not call the backend,
  persist, dispatch, use clipboard APIs, or open apps.

Types live in `lib/operator-packet-review-types.ts`, data in
`lib/operator-packet-review-mock-data.ts`. The UI remains static and local:
no packet is automatically dispatched and operator approval is always required.

## Stage 5.6 - Cross-Agent Workflow Router Mock

The "Cross-Agent Router (Stage 5.6)" section previews the cross-agent
workflow router implemented in `scos/control_center/workflow_router_models.py`,
`workflow_router.py`, and `workflow_route_store.py` with static
deterministic mock data only:

- Workflow Router panel: a sample routing decision (source/target agent,
  next packet type) computed by the default route rules.

Types live in `lib/workflow-router-types.ts`, data in
`lib/workflow-router-mock-data.ts`. No route plan here is dispatched or
executed - the router only computes which agent/packet type should come
next, and every step remains display-only data.

## Stage 5.7 - AI Result Intake & ChatGPT Status Update Loop Mock

The "Result Intake" section previews the local result-intake loop implemented
in `scos/control_center/result_intake_*.py`, `chatgpt_status_update.py`, and
`project_state_update.py` with static deterministic mock data only:

- Result Intake panel: pasted/imported results from Claude Code, Codex,
  Hermes, ChatGPT, and the operator, each with a verdict badge (PASS / FAIL /
  BLOCKED / NEEDS_FIX / NEEDS_REVIEW / PARTIAL), normalized summary,
  blockers/warnings, artifacts/evidence, and an operator-review-required flag.
- ChatGPT Status Update panel: the generated manual-handoff status update
  body, requested ChatGPT action, and evidence references, with an inert
  "copy manually — no clipboard access" control.
- Project State Update panel: current stage, task status, stage status,
  latest agent/verdict, and evidence references derived from the selected
  intake.
- Next Action Decision panel: recommended action, target agent/runtime,
  priority, reason, and an always-visible operator-approval requirement.

Selecting a card in the Result Intake list updates React local state only.
Types live in `lib/result-intake-types.ts`, data in
`lib/result-intake-mock-data.ts`. Nothing here calls a network API, dispatches
an AI agent, reads/writes a clipboard, or automates a browser/app — every
result must be pasted in and every next action approved by the operator.

## Stage 5.8 - Git Commit / Push Approval Gate Mock

The "Commit/Push Gate" section previews the local commit/push approval gate
implemented in `scos/control_center/git_approval_models.py`,
`git_evidence_snapshot.py`, `git_approval_builder.py`, and
`git_approval_store.py` with static deterministic mock data only:

- Git Evidence Summary panel: branch, HEAD, origin/main, changed files, test
  evidence (pass/fail), remote-only-commits flag, and risk flags.
- Commit Proposal card: conventional-commit message, sorted files-to-commit,
  evidence/test summaries, computed risk level, an always-visible
  "approval required" badge, and inert Approve / Reject / Needs Changes
  controls.
- Push Approval panel: ahead/behind counts, remote/refspec, the proposed
  `git push origin main` command, a note that force push/tags/releases can
  never be generated, and an inert Approve Push control that stays disabled
  until the commit decision above is approved.
- Git Decision Log panel: the append-only event timeline mirroring
  `GitApprovalStore`, showing the proposal lifecycle so far.

Types live in `lib/git-approval-types.ts`, data in
`lib/git-approval-mock-data.ts`. Nothing here calls a network/GitHub API,
runs `git add`/`git commit`/`git push`, reads/writes a clipboard, or
automates a terminal — every proposed command is inert guidance text the
operator must type themselves, and the push proposal always stays locked
until the operator's commit approval decision is recorded as approved.

## Stage 5.9 - Operator Execution Console / Manual Command Runbook Mock

The "Execution Console" section previews the local operator execution layer
implemented in `scos/control_center/operator_execution_models.py`,
`operator_execution_runbook.py`, and `operator_execution_store.py` with static
deterministic mock data only. It answers: once a manual/proposed command is
approved, how does the operator safely see the exact command, run the required
pre-checks, run it manually outside SCOS, paste the result back, classify the
outcome, and preserve deterministic evidence?

- Boundary banner: SCOS does not execute commands; the operator runs them
  manually; approval is required; push approval is separate from commit
  approval; results are pasted back manually; blocked/failed results route
  back to review.
- Manual Command Runbook panel: ordered command steps (shell, working
  directory, risk badge, expected-result hint) with "Manual copy required" and
  "Operator confirmation required" labels. One commit runbook (6 steps), one
  push runbook (11 steps), and one blocked verification runbook are shown.
- Execution Safety Checklist: required pre-checks with severity and
  pending/passed/failed/requires_review status plus an operator instruction.
- Command Result Capture panel: pasted output summary, raw output excerpt,
  exit-status text, verdict (PASS / PASS_WITH_WARNINGS / NEEDS_REVIEW /
  BLOCKED / FAIL / UNKNOWN), warnings/blockers, evidence paths, and the
  recommended next action (e.g. update ChatGPT status, route to Codex, or
  operator manual review).

Types live in `lib/operator-execution-types.ts`, data in
`lib/operator-execution-mock-data.ts`. There is no `navigator.clipboard`, no
`fetch`, no terminal, no timers, and no storage — the "copy" affordance is
inert text, and every command is guidance the operator must run themselves.

## Stage 5.10 - Stage 5 Final AI Command Center Certification Mock

The "Stage 5 Final Certification" section previews the read-only Stage 5.10
certification gate implemented in
`scos/control_center/stage5_final_certification.py` with static
deterministic mock data only. It answers: is Stage 5 complete, internally
consistent, locally verifiable, and safe from real AI dispatch / network /
automation overreach?

- Verdict banner: GO / NO_GO badge plus the readiness score and level.
- Blockers panel: every named, severity-ranked finding the gate surfaced,
  including the two real, confirmed Stage 5.6 defects it does not fix (the
  package export gap and the duplicate `ALLOWED_COMMAND_TYPES` lazy-export
  key).
- Check matrix: every Stage 5.1-5.9 certification check with its status,
  category, and severity.
- Stage 6 Handoff panel: the 10 deterministic handoff items the gate
  generates for the next stage.

Types live in `lib/stage5-certification-types.ts`, data in
`lib/stage5-certification-mock-data.ts`. This panel never fixes a finding —
it only mirrors what the read-only gate reported; nothing here dispatches
AI work, calls a network API, or automates a browser/GUI/clipboard.

## Stage 6.2 - Local Control Center Backend & Command API Mock

The "Local Backend / Command API (Stage 6.2)" section previews the first
local backend command boundary implemented in `scos/control_center/`
(`backend_models.py`, `backend_validation.py`, `command_api.py`,
`local_backend.py`, `backend_response_builder.py`) with static
deterministic mock data only. It answers: can SCOS expose a safe local
backend command boundary that validates requests and produces
deterministic responses, without yet adding SQLite, WebSocket, an event
stream, or real AI dispatch?

- Local Backend status panel: `Stage 6.2 Foundation Ready` banner, active
  store (`in_memory_only`), event stream status
  (`disabled_until_stage_6_4`), SQLite WAL status (disabled until Stage
  6.3), and real adapter dispatch status (disabled).
- Command API panel: four action cards -- Health Check, Preview Command,
  Validate Command, Dry-run Enqueue -- each showing its request and a
  rendered `BackendResponseCard`.
- Rejected example: an unknown command type rejected deterministically,
  with the `BackendError` detail and recommended action shown.
- Operator approval notice: real queueing/execution still requires the
  Stage 5.1 draft -> validate -> operator approval -> queue -> runner
  pipeline; this panel only previews/validates/dry-runs.

## Stage 6.3 - Durable Local State Store (SQLite WAL) Mock

The "Durable State (SQLite) (Stage 6.3)" section previews the first
durable local state layer implemented in `scos/control_center/`
(`state_models.py`, `sqlite_state_schema.py`, `sqlite_state_store.py`,
`state_repository.py`, `state_snapshot.py`) with static deterministic mock
data only. It answers: can SCOS persist Control Center state locally and
deterministically, so a future Stage 6.4 event stream/UI sync has real
local state to read from?

- Durable State status panel: store status (`ready_for_stage_6_4`),
  database path (`scos/work/control_center/state/control_center.sqlite3`),
  WAL mode (`enabled`), event stream status (`disabled_until_stage_6_4`),
  real adapter dispatch status (disabled), and backend socket server
  status (disabled).
- State Snapshot panel: example deterministic snapshot with WAL
  verification, per-table counts (commands/sessions/events/approvals/
  results), and the explicit Stage 6.4 disabled-capabilities list
  (websocket, sse, polling, real adapter dispatch, arbitrary command
  execution, Next.js API routes).
- Example persistence records: a `DurableCommandRecord` card and a
  `DurableApprovalRecord` card showing the shape of what the real SQLite
  store persists.
- This panel never opens a database connection from the frontend -- the
  real SQLite WAL store lives entirely in the Python backend behind the
  Stage 6.2 command boundary.

Types live in `lib/local-backend-types.ts`, data in
`lib/local-backend-mock-data.ts`. This panel never calls `fetch`, opens a
socket, starts a timer, reads a real clock/random value, or touches
browser storage -- everything shown is a hand-authored constant.

## Stage 6.4 - Local Event Stream & UI State Sync Foundation Mock

The "Event Stream / UI Sync (Stage 6.4)" section previews the first local
event stream and UI state sync foundation implemented in
`scos/control_center/` (`event_stream_models.py`, `event_stream_builder.py`,
`event_stream_snapshot.py`, `ui_state_sync.py`) with static deterministic
mock data only. It answers: can Control Center read durable local state,
expose deterministic event snapshots, and prepare UI state sync without
using WebSocket, SSE, polling, timers, backend sockets, network APIs, or
real adapter dispatch?

- Sync Health panel: a healthy/blocked banner plus any blockers/warnings
  carried from the underlying snapshots.
- UI State Sync panel: sync status, active stage/task, backend status,
  durable state status, latest event id/sequence, and any pending operator
  actions.
- Event Stream panel: a deterministic cursor-based batch of 5 example local
  events (command lifecycle, session, approval, UI-sync-ready) each with a
  sequence number, type, entity, status, and timestamp.
- Snapshot Metadata card: schema version, snapshot id, and status/source
  counts derived from the same event batch.
- This is a snapshot/summary foundation only, gated behind a Phase A
  regression triage (`docs/certification/Stage-6.4-regression-triage.md`)
  that confirmed no pre-existing Stage 5/6 regression blocks this stage.
  See `docs/specification/STAGE6_EVENT_STREAM_BOUNDARY.md` for why
  WebSocket/SSE/polling are deferred to a later stage.

Types live in `lib/event-stream-types.ts` and `lib/ui-state-sync-types.ts`,
data in `lib/event-stream-mock-data.ts`. This panel never calls `fetch`,
opens a socket, starts a timer, reads a real clock/random value, or touches
browser storage -- everything shown is a hand-authored constant.

## Stage 7.6 - Approval-Aware Command Views Mock

The "Command Evidence" section previews the Stage 7.6 approval-aware command
view and read-only execution evidence surface implemented in
`scos/control_center/operator_command_view*.py` and
`scos/control_center/execution_evidence_surface.py` with static deterministic
mock data only.

- Command evidence cards show command id, command type, approval state,
  execution evidence state, audit state, terminal-state indicator, required
  manual action, blockers, warnings, and evidence references.
- The fixture includes pending, approved, denied, missing approval, executed,
  and blocked command instances.
- Denied and missing-approval examples are terminal for the current command
  instance.
- The execution evidence panel summarizes blocked and terminal instances
  without offering any bypass action.

Types live in `lib/operator-command-view-types.ts`, data in
`lib/operator-command-view-mock-data.ts`. The UI remains static and local:
there are no approval controls, no denial controls, no command-running
controls, no network path, and no live transport behavior.

## Tech Stack

- Next.js 15 App Router + React 19
- TypeScript strict mode
- Tailwind CSS v4 with `@tailwindcss/postcss`
- No external UI library, no 3D library, no remote assets

## Getting Started

All commands run from this directory (`apps/control-center/`):

```bash
pnpm install
pnpm dev
```

Validate:

```bash
pnpm lint
pnpm build
```

Static validation should also confirm no hand-authored executable source contains
network calls, server actions, runtime clocks/randomness, browser storage,
clipboard APIs, timers, API routes, middleware, or route handlers.

## Responsive Layout

The layout adapts across breakpoints so selection feedback and the task board stay
usable at every width:

| Width | Navigation | Task board | Task Detail + Orbit |
| --- | --- | --- | --- |
| xl+ (1280+) | Left sidebar | 6-column grid | Right rail with full Orbit |
| lg (1024-1279) | Left sidebar | Horizontal-scroll columns | In-flow below board |
| md (768-1023) | Compact top-nav | Horizontal-scroll columns | In-flow below board |
| sm (<768) | Compact top-nav | Horizontal-scroll columns | Stacked in-flow |

The right rail and in-flow selected-task section render from the same selected task
state. Horizontal scrolling is intentionally confined to the task board.

## Interactions

- Click any task from the board, agent cards, inbox, merge queue, or timeline to
  update Task Detail and Orbit.
- Prompt Builder lets the operator choose a target agent and template; the prompt
  preview is read-only and sending is disabled.
- Result Inbox includes a display-only manual paste placeholder and static route
  guidance.
- Merge Queue shows disabled Approve / Request Fix / Reject / Hold controls plus
  static Decision Guidance.

## Orbit

`components/mascot-assistant.tsx` renders a CSS-only floating orb whose mood
reacts to the selected task. Orbit now gives workflow advice: what panel to use,
when to ask Codex, when to hold merge, and when not to proceed.

## Data & Determinism

All mock data lives in `lib/mock-data.ts`; all shared types live in `lib/types.ts`.
The source performs no network calls, uses no runtime clock or randomness, and
defines no API routes or server actions. Timestamps are hardcoded ISO-8601 strings.

Includes: 4 agents, 9 tasks, one primary next action, 5 handoff steps, 6 timeline
events, 4 merge items with Decision Guidance, and 4 result items with route
guidance.
