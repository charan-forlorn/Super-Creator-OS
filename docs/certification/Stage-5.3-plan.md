# Stage 5.3 — AI Agent Adapter Contract Layer (Plan)

## Stage goal

Create the AI Agent Adapter Contract Layer: a deterministic contract that
represents, validates, and simulates the request/result lifecycle for
handing one AI work item to ChatGPT, Claude Code, Codex, Hermes, or the
manual clipboard fallback, without dispatching real work to any of them.
Stage 5.3 answers:

> Can SCOS represent, validate, and simulate an AI adapter request/result
> lifecycle for each target AI runtime without coupling to any specific app
> implementation?

Stage 5.3 sits above the Stage 5.2 Work Session Manager and below any
future real AI integration. It does not dispatch real work, call any API,
automate a desktop app, drive a browser, drive a GUI, or touch a
clipboard.

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, Stage
5.3 belongs to the Development Framework Layer. It must not move
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
- working tree clean
- latest history includes the Stage 5.2 AI Work Session Manager

If preflight fails: stop, report, change nothing.

## Implementation scope

- New modules in the existing stdlib-only `scos/control_center/` package:
  `agent_adapter_models`, `agent_adapter_contracts`,
  `agent_adapter_registry`, `agent_adapter_simulator`.
- Five immutable dataclasses (`AgentAdapterCapability`,
  `AgentAdapterRequest`, `AgentAdapterResult`, `AgentAdapterError`,
  `AgentAdapterSimulationEvent`) following the same frozen-dataclass +
  `_require_allowed` + tuple-of-pairs-metadata convention established by
  Stage 5.2's `work_session_models.py`.
- `BaseAgentAdapter` contract plus five contract-only adapters
  (`ChatGPTContractAdapter`, `ClaudeCodeContractAdapter`,
  `CodexContractAdapter`, `HermesContractAdapter`,
  `ManualClipboardContractAdapter`), each declaring capability data only —
  no I/O in any adapter method.
- `AgentAdapterRegistry` + `create_default_agent_adapter_registry()`:
  deterministic lookup, capability-based selection, and task-type routing
  with a guaranteed `manual_clipboard` fallback.
- `simulate_agent_adapter_request` / `simulate_adapter_lifecycle`: pure,
  deterministic simulation of the full request -> result lifecycle,
  producing an ordered tuple of `AgentAdapterSimulationEvent`s.
- Contracts: `AI_AGENT_ADAPTER_CONTRACT.md`,
  `AI_AGENT_ADAPTER_REGISTRY_CONTRACT.md`.
- Static mock UI panels in `apps/control-center` (adapter capability cards,
  simulated lifecycle) using deterministic mock data only.

## Allowed files

Create only:

- `scos/control_center/agent_adapter_models.py`,
  `agent_adapter_contracts.py`, `agent_adapter_registry.py`,
  `agent_adapter_simulator.py`
- `scos/control_center/tests/test_agent_adapter_models.py`,
  `test_agent_adapter_contracts.py`, `test_agent_adapter_registry.py`,
  `test_agent_adapter_simulator.py`
- `docs/specification/AI_AGENT_ADAPTER_CONTRACT.md`,
  `AI_AGENT_ADAPTER_REGISTRY_CONTRACT.md`
- `docs/certification/Stage-5.3-plan.md`

Frontend (only because `apps/control-center` exists): create
`lib/agent-adapter-types.ts`, `lib/agent-adapter-mock-data.ts`,
`components/agent-adapter-panel.tsx`, `components/adapter-contract-card.tsx`,
`components/adapter-simulation-panel.tsx`; modify
`components/app-shell.tsx`, `components/sidebar.tsx`, `README.md` for wiring
only.

Optional: `scos/control_center/__init__.py` — preserve lazy PEP 562
exports, additive only.

## Hard constraints (non-negotiable)

- Python stdlib only; local-first only; deterministic outputs only.
- No AI execution, no API calls, no MCP, no WebSocket, no SQLite/database,
  no HTTP server, no browser automation, no GUI automation, no OS app
  control, no clipboard automation, no background worker, no scheduler, no
  polling, no git execution (no commit/push), no
  SaaS/CRM/payment/cloud/customer portal.
- No Runtime Product Layer changes (`scos/pipeline`, `scos/render`,
  `scos/core`, `scos/commercial`, `scos/qualification`, `scos/learning`,
  `scos/knowledge`, `scos/repository`, `scos/replay`, `scos/analytics`),
  and no Stage 4, Stage 5.1, or Stage 5.2 public contract broken.
- No clock/random/uuid in Stage 5.3 modules; every timestamp and id is
  caller-supplied.
- `prompt_text` is rejected at the model layer if it contains a
  `http://`/`https://` URL/network target.
- Frontend: no backend calls, no fetch/XHR/WebSocket/EventSource, no
  storage, no `setInterval`/`setTimeout`/`Date.now()`/`Math.random()`/
  `crypto.randomUUID()`, no new dependencies, no real agent dispatch from
  the UI — static deterministic mock data only.
- No commit / push / tag / release. Implement, test, report, stop.

## Required test commands

```
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_contracts.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_simulator.py
```

Re-run Stage 5.1/5.2 regression suite:

```
.venv\Scripts\python.exe scos\control_center\tests\test_command_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_validation.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_approval.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_queue.py
.venv\Scripts\python.exe scos\control_center\tests\test_event_log.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_runner.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_runtime_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_manager.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_store.py
```

Release/safety checks, if practical:

```
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
```

## Frontend validation

From `apps/control-center`:

```
npm run lint
npm run build
```

(Repo uses `npm`, not `pnpm` — confirmed against the Stage 5.2 plan doc and
`package.json`.)

## Static scan checklist

Python (`agent_adapter_*.py` + their tests): no `requests`,
`urllib.request`, `http.client`, `websocket`, `selenium`, `playwright`,
`pyautogui`, `subprocess` (as an import/call), `os.system`, `shell=True`,
real clipboard access, or environment probing for installed AI apps.

Frontend (`agent-adapter-*` lib/components + touched shell/sidebar files):
no `fetch(`, `XMLHttpRequest`, `axios`, `WebSocket`, `EventSource`,
`setInterval`, `setTimeout`, `Date.now`, `Math.random`,
`crypto.randomUUID`, `localStorage`, `sessionStorage`, `"use server"`,
`app/api`, `route.ts`, `middleware.ts`.

## Safety checks

- `python -c "import scos.control_center as cc; cc.create_default_agent_adapter_registry()"`
  sanity import check confirming lazy `__init__.py` wiring.
- Confirm `manual_clipboard` is present, enabled, and covers every allowed
  task type in both the registry and the frontend mock data.
- Confirm no Stage 5.1/5.2 public export was removed or renamed in
  `scos/control_center/__init__.py`.

## Completion report template

- Verdict: PASS / BLOCKED
- Files created / modified (exact list)
- Tests run + results (per-script pass/fail counts)
- Frontend validation results
- Static scan results
- Architecture notes: no Runtime Product Layer import, boundary
  constitution respected, no Stage 5.1/5.2 contract break
- Known limitations
- Recommended next stage: Stage 5.4 — Unified Prompt & Result Packet
