# SCOS Agent Control Center — v0.1 (Frontend Prototype)

A dark-mode desktop dashboard for a solo operator coordinating the four SCOS agents
during stage-gated development:

| Agent        | Role                          |
| ------------ | ----------------------------- |
| ChatGPT      | Orchestrator                  |
| Claude Code  | Builder                       |
| Codex        | Reviewer / Verifier           |
| Hermes       | Repo Health / Workflow Auditor|

The interface is designed to answer, at a glance:

1. **What stage are we on?** — top bar + Stage Progress panel.
2. **Which agent is active?** — active-agent chip + Agent Status cards.
3. **What task is blocked?** — Blocked column + red Orbit glow + Task Detail.
4. **What result is ready for review?** — Result Inbox (PASS/FAIL) + Merge Queue.
5. **What should the operator do next?** — Orbit's recommended next action.

> **This is a frontend prototype only.** It is 100% local-first: static mock data,
> React local state, and a CSS-only animated mascot ("Orbit"). There is **no backend,
> no database, no API routes, no network requests, no auth.**

## Tech stack

- **Next.js 15** (App Router) + **React 19**
- **TypeScript** (strict)
- **Tailwind CSS v4** (`@tailwindcss/postcss`)
- No external UI library, no 3D library, no remote assets.

## Getting started

All commands run **from this directory** (`apps/control-center/`):

```bash
pnpm install
pnpm dev      # http://localhost:3000
```

Validate:

```bash
pnpm lint
pnpm build
```

> If pnpm is unavailable, the identically-named scripts work with npm:
> `npm install`, `npm run lint`, `npm run build`.

## Layout

```
┌───────────┬─────────────────────────────────────────────┬──────────────┐
│  Sidebar  │  Top bar (title · stage · active agent)      │              │
│  (nav)    ├─────────────────────────────────────────────┤  Task Detail │
│           │  Overview: Agent cards + Stage Progress      │   (selected) │
│  Overview │  Task Board (kanban by status)               │              │
│  Board    │  Prompt Builder (target agent + template)    │  Orbit       │
│  Prompt   │  Result Inbox    |    Merge Queue            │  (mascot)    │
│  Inbox    │  Timeline (recent activity)                  │              │
│  Merge    │                                             │              │
│  Timeline │                                             │              │
└───────────┴─────────────────────────────────────────────┴──────────────┘
```

The right rail (Task Detail + Orbit) is shown on wide (`xl`) desktop viewports.

## Orbit, the mascot

`components/mascot-assistant.tsx` renders a friendly CSS-only floating orb whose glow
reacts to the **selected task's** status:

| Task status  | Orbit mood        | Glow            |
| ------------ | ----------------- | --------------- |
| in-progress  | working           | amber pulse     |
| blocked      | blocked           | red warning     |
| in-review    | review / thinking | violet          |
| approved/done| approved          | green success   |
| backlog/none | idle              | calm grey       |

Orbit's panel shows its name, a short status message, a recommended next operator
action, and a one-line summary of the selected task — all derived deterministically in
`lib/utils.ts` (`deriveMascotView`).

## Interactions

- **Click any task** (board card, agent card, inbox/merge/timeline row) → updates the
  Task Detail Panel **and** Orbit's mood/message/next action.
- **Prompt Builder** → pick a target agent + template; the preview updates. Sending is
  intentionally disabled (prototype).
- **Merge Queue** → Approve / Request Fix / Reject / Hold are rendered disabled; no
  action ever executes.

## Data & determinism rules (enforced)

All mock data lives in [`lib/mock-data.ts`](lib/mock-data.ts); all types in
[`lib/types.ts`](lib/types.ts). The source performs **no** network calls, uses **no**
runtime clock or randomness, and defines **no** API routes or server actions — so the
UI is fully deterministic. Timestamps are hardcoded ISO-8601 strings.

Includes: 4 agents · 9 tasks (one blocked, one approved, tasks in review assigned to
Codex, tasks assigned to Claude Code and Hermes) · 6 timeline events · 4 merge items ·
4 result items.
