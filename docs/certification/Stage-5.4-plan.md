# Stage 5.4 — Unified Prompt & Result Packet (Plan)

## Stage goal

Create a unified, deterministic packet contract for passing prompts and
results between AI agents. Stage 5.4 answers:

> How does SCOS package a task prompt for one AI, preserve context/evidence,
> receive the result, validate it, and route it to the next AI without
> losing traceability?

Stage 5.4 creates the packet layer only — models, a builder, a JSONL store,
docs, tests, and a static frontend mock. It supports (as pure data, never
executed) the flow: ChatGPT plans -> Claude Code implements -> Codex
reviews -> Hermes audits -> ChatGPT summarizes, with FAIL/BLOCKED verdicts
escalating to an operator manual-handoff packet at any stage.

## Scope

- New modules in `scos/control_center/`: `prompt_result_packet_models.py`,
  `prompt_result_packet_builder.py`, `prompt_result_packet_store.py`.
- Six immutable dataclasses (`PacketContextReference`, `PromptPacket`,
  `ResultArtifactReference`, `ResultPacket`, `PacketRoutingDecision`,
  `PromptResultPacketError`) following the frozen-dataclass +
  `_require_allowed` + tuple-of-pairs-metadata convention established by
  Stage 5.2/5.3.
- Four builder functions (`create_prompt_packet`, `create_result_packet`,
  `create_routing_decision`, `create_followup_prompt_from_result`) plus a
  pure routing-recommendation lookup (`recommend_routing`).
- A JSONL append-only store (six functions: three `append_*`, three
  `load_*`) reusing the existing `command_queue.py` primitives.
- Contracts: `UNIFIED_PROMPT_RESULT_PACKET_CONTRACT.md`,
  `AI_PACKET_ROUTING_CONTRACT.md`.
- Static mock UI panels in `apps/control-center` (prompt/result packet
  cards, a 5-stage routing flow) using deterministic mock data only.

## Non-goals

This stage does NOT send prompts to real AI apps, does NOT read a
clipboard, does NOT automate a browser/app/GUI, does NOT call
ChatGPT/Claude/Codex/Hermes, does NOT use network/API/cloud, does NOT
introduce a database, WebSocket, background worker, or real-time server,
and does NOT touch Stage 4, Stage 5.1, Stage 5.2, or Stage 5.3 public
contracts. A broader "AI Personal/Project Knowledge Base" concept (decision
logs, preference evolution, AI interaction history) was raised during
planning and is explicitly out of scope for this stage — see "Recommended
next stage" below.

## Files created

- `scos/control_center/prompt_result_packet_models.py`
- `scos/control_center/prompt_result_packet_builder.py`
- `scos/control_center/prompt_result_packet_store.py`
- `scos/control_center/tests/test_prompt_result_packet_models.py`
- `scos/control_center/tests/test_prompt_result_packet_builder.py`
- `scos/control_center/tests/test_prompt_result_packet_store.py`
- `docs/specification/UNIFIED_PROMPT_RESULT_PACKET_CONTRACT.md`
- `docs/specification/AI_PACKET_ROUTING_CONTRACT.md`
- `docs/certification/Stage-5.4-plan.md` (this file)
- `apps/control-center/lib/prompt-result-packet-types.ts`
- `apps/control-center/lib/prompt-result-packet-mock-data.ts`
- `apps/control-center/components/prompt-result-packet-panel.tsx`
- `apps/control-center/components/prompt-packet-card.tsx`
- `apps/control-center/components/result-packet-card.tsx`
- `apps/control-center/components/packet-routing-flow.tsx`

## Files modified

- `scos/control_center/__init__.py` — additive-only `_LAZY_EXPORTS` entries
  for the new modules; no existing entry removed or reordered.
- `apps/control-center/components/app-shell.tsx` — new `#prompt-packets`
  section, placed after the existing `#agent-adapters` section.
- `apps/control-center/components/sidebar.tsx` — new `NAV_SECTIONS` entry
  for "Prompt Packets".
- `apps/control-center/README.md` — new Stage 5.4 bullet.

## Architecture boundary

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, this
module belongs to the Development Framework Layer. No Runtime Product Layer
file (`scos/pipeline`, `scos/render`, `scos/core`, `scos/commercial`,
`scos/qualification`, `scos/learning`, `scos/knowledge`, `scos/repository`,
`scos/replay`, `scos/analytics`) was read, imported, or modified. No Stage
4, Stage 5.1, Stage 5.2, or Stage 5.3 public contract was changed — all 14
pre-existing `scos/control_center/tests/*.py` files pass unchanged.
`prompt_result_packet_models.py` duplicates its own private helpers
(`_require_allowed`, `_string_pairs`, etc.) rather than importing them from
`work_session_models.py`/`agent_adapter_models.py`, matching the
established per-file convention.

## Test commands

```
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_builder.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_store.py
```

Stage 5.1-5.3 regression (all 14 pre-existing test files):

```
.venv\Scripts\python.exe scos\control_center\tests\test_command_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_validation.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_approval.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_queue.py
.venv\Scripts\python.exe scos\control_center\tests\test_event_log.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_runner.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_runtime_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_manager.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_contracts.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_simulator.py
```

Release/safety checks:

```
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
```

Package import + lazy-export sanity:

```
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'scos'); from control_center import PromptPacket, ResultPacket, PacketRoutingDecision, PromptResultPacketError, create_prompt_packet, create_result_packet, create_routing_decision, create_followup_prompt_from_result, recommend_routing, append_prompt_packet, load_prompt_packets; print('OK')"
```

## Frontend validation

From `apps/control-center`:

```
pnpm lint
pnpm build
```

Visual check (dev server): a new "Prompt Packets" entry appears in the
sidebar after "Agent Adapters"; the `#prompt-packets` section renders all 6
mock scenarios (5 named agent-to-agent handoffs plus 1 blocked/operator-review
case) as prompt/result card pairs, and a 5-stage routing flow chip strip
(ChatGPT -> Claude Code -> Codex -> Hermes -> ChatGPT).

## Static scan

Python (`prompt_result_packet_*.py` + their tests): no `requests`,
`urllib.request`, `http.client`, `websocket`, `selenium`, `playwright`,
`pyautogui`, `subprocess` (as an import/call), `os.system`, `shell=True`,
real clipboard access.

Frontend (new `prompt-result-packet-*` lib/components + touched
shell/sidebar files):

```
grep -RnE "fetch\(|XMLHttpRequest|axios|WebSocket|EventSource|setInterval|setTimeout|Date\.now|Math\.random|crypto\.randomUUID|localStorage|sessionStorage|navigator\.clipboard|use server|app/api|route\.ts|middleware\.ts" apps/control-center/lib/prompt-result-packet-types.ts apps/control-center/lib/prompt-result-packet-mock-data.ts apps/control-center/components/prompt-result-packet-panel.tsx apps/control-center/components/prompt-packet-card.tsx apps/control-center/components/result-packet-card.tsx apps/control-center/components/packet-routing-flow.tsx
```

Expected: no matches.

## Acceptance criteria

- [x] `PromptPacket` model exists and serializes deterministically
- [x] `ResultPacket` model exists and serializes deterministically
- [x] `PacketContextReference` model exists and serializes deterministically
- [x] `ResultArtifactReference` model exists and serializes deterministically
- [x] `PacketRoutingDecision` exists and serializes deterministically
- [x] packet ids are deterministic sha256 from stable inputs (pinned in
      `test_prompt_result_packet_builder.py` tests 1 and 9)
- [x] `created_at` is caller-supplied only; no real clock/random/uuid
      (static-source check, test 13)
- [x] invalid agent/packet/result/verdict returns a deterministic
      `PromptResultPacketError` (tests 3, 4, 8)
- [x] URL paths are rejected (models test 5, builder covers via model)
- [x] secret-like metadata keys are rejected (models test 6)
- [x] prompt packet buildable for ChatGPT -> Claude Code (builder test 1)
- [x] result packet buildable for Claude Code -> Codex (builder test 12)
- [x] routing decision routes Codex NEEDS_FIX back to Claude Code (builder
      tests 11, 12)
- [x] routing decision routes Codex PASS to Hermes audit (builder test 12)
- [x] routing decision routes Hermes PASS to ChatGPT status update (builder
      test 12)
- [x] blocked/fail routes to operator/manual handoff (builder tests 11, 12)
- [x] JSONL packet store writes deterministic lines (store test 2-4)
- [x] JSONL packet store loads packets deterministically, append-only, no
      de-dup (store test 8)
- [x] frontend displays prompt packet state
- [x] frontend displays result packet state
- [x] frontend displays packet routing flow
- [x] frontend has no real AI dispatch
- [x] frontend has no backend/API/network/timer/storage/random/clipboard
      behavior (static scan)
- [x] no Stage 4 public contracts modified
- [x] no Stage 5.1/5.2/5.3 public contracts broken (regression suite green)
- [x] no `scos/knowledge` implementation files modified
- [x] all tests pass (see Test results in the final report)

## Known limitations

- No state-machine enforcement of `PromptPacket.status`/`ResultPacket.status`
  transitions — Stage 5.4 models the allowed value sets but does not (yet)
  provide a `transition_*` function analogous to
  `work_session_manager.transition_status`.
- Routing recommendations are advisory data only; nothing consumes a
  `PacketRoutingDecision` to automatically create the next `PromptPacket` —
  that remains an explicit, separate caller action.
- The spec's storage description mentions "sort_keys"; this store achieves
  deterministic JSONL output via each model's explicit `to_dict()` key
  order instead, since the shared `_append_jsonl_line` primitive (reused
  as-is from `command_queue.py`) does not pass `sort_keys=True`. Documented
  in `UNIFIED_PROMPT_RESULT_PACKET_CONTRACT.md`.
- No persistence beyond local JSONL; no UI wiring between the Python
  backend and the frontend mock (frontend remains static mock data, per
  spec).

## Recommended next stage

Stage 5.5 — Operator Packet Review & Manual Handoff Flow (a review/approval
UI and state-machine layer over the packets and routing decisions created
here, still local-first and still gated by explicit operator action).

A broader "AI Personal/Project Knowledge Base" (APKB) direction was also
raised during Stage 5.4 planning — a persistent decision log with
rationale, preference-evolution tracking over time, and AI interaction /
prompt-effectiveness history. This is a materially larger, separate
initiative (it would require persistent storage/analytics beyond a local
JSONL packet log) and is not scoped into Stage 5.5; it may be considered as
its own future stage once Stage 5.5 is complete.
