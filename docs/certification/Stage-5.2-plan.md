# Stage 5.2 — AI Work Session Manager (Plan)

## Stage goal

Create a deterministic local AI Work Session Manager: the orchestration
foundation for coordinating work across ChatGPT, Claude Code, Codex, and
Hermes, answering:

> Can an operator create a task, assign it to a declared AI runtime, track
> its status through a fixed lifecycle, collect a result, and hand that
> result to another AI — as pure, deterministic local state, with no AI
> execution and no automation of any kind?

Stage 5.2 models AI work. It does not execute AI, call any API, automate a
desktop app, drive a browser, or drive a GUI.

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, Stage
5.2 belongs to the Development Framework Layer. It must not move
orchestration logic into the Runtime Product Layer, and it must not alter
Runtime Product Layer behavior.

## Preflight

Run and require ALL of:

```
git fetch origin
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/main
git branch --show-current
git log --oneline -10
```

- current branch is `main`
- `HEAD == origin/main`
- working tree clean (aside from expected untracked Stage 5.2A output)
- latest history includes the Stage 5.1 local command bridge

If preflight fails: stop, report, change nothing.

## Implementation scope

- New modules in the existing stdlib-only `scos/control_center/` package:
  `work_session_models`, `runtime_registry`, `work_session_manager`,
  `work_session_store`.
- Deterministic lifecycle: `AIWorkTask -> AIWorkSession (draft) ->
  AgentAssignment -> status transitions -> done`, with `cancelled` reachable
  from any non-terminal status.
- Static built-in runtime registry covering ChatGPT, Claude Code, Codex,
  Hermes, plus the always-enabled `manual_clipboard` fallback.
- JSONL append-only session/event store (no SQLite, no database).
- Contracts: `AI_WORK_SESSION_MANAGER_CONTRACT.md`,
  `AI_AGENT_RUNTIME_REGISTRY_CONTRACT.md`.
- Static mock UI panels in `apps/control-center` (AI work sessions, agent
  routing, agent result status) using deterministic mock data only.

## Allowed files

Create only:

- `scos/control_center/work_session_models.py`, `work_session_manager.py`,
  `work_session_store.py`, `runtime_registry.py`
- `scos/control_center/tests/test_work_session_models.py`,
  `test_work_session_manager.py`, `test_work_session_store.py`,
  `test_runtime_registry.py`
- `docs/specification/AI_WORK_SESSION_MANAGER_CONTRACT.md`,
  `AI_AGENT_RUNTIME_REGISTRY_CONTRACT.md`
- `docs/certification/Stage-5.2-plan.md`

Frontend (only because `apps/control-center` exists): create
`lib/ai-work-session-types.ts`, `lib/ai-work-session-mock-data.ts`,
`components/ai-work-session-panel.tsx`, `components/agent-routing-panel.tsx`,
`components/agent-result-status-panel.tsx`; modify
`components/app-shell.tsx`, `components/sidebar.tsx`, `README.md` for wiring
only.

Optional: `scos/control_center/__init__.py` — preserve lazy PEP 562 exports,
additive only.

## Hard constraints (non-negotiable)

- Python stdlib only; local-first only; deterministic outputs only.
- No AI execution, no API calls, no MCP, no WebSocket, no SQLite/database,
  no HTTP server, no browser automation, no GUI automation, no background
  worker, no scheduler, no git execution (no commit/push), no
  SaaS/CRM/payment/cloud.
- No Runtime Product Layer changes (`scos/pipeline`, `scos/render`,
  `scos/core`, `scos/commercial`, `scos/qualification`, `scos/learning`,
  `scos/knowledge`, `scos/repository`, `scos/replay`, `scos/analytics`),
  and no Stage 4 or Stage 5.1 artifact modified.
- No clock/random/uuid in Stage 5.2 modules; every timestamp and id is
  caller-supplied.
- Frontend: no backend calls, no fetch/XHR, no storage, no `Date.now()` /
  `Math.random()` / `crypto.randomUUID()`, no new dependencies, no real
  agent dispatch from the UI — static deterministic mock data only.
- No commit / push / tag / release. Implement, test, report, stop.

## Required test commands

```
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_runtime_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_manager.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_validation.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_approval.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_queue.py
.venv\Scripts\python.exe scos\control_center\tests\test_event_log.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_runner.py
```

If frontend files changed, from `apps/control-center`:

```
npm run lint
npm run build
```

## Completion report template

- Verdict: PASS / FAIL
- Files created / modified (exact list)
- Commands run + results (per-test pass/fail counts)
- Architecture compliance: no Runtime Product Layer import, boundary
  constitution respected
- Confirmations: no AI execution/API/MCP/WebSocket/database/network/GUI or
  browser automation; no Stage 4/5.1 modification; no commit/push/tag
- Known follow-up work for Stage 5.3
