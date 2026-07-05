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
