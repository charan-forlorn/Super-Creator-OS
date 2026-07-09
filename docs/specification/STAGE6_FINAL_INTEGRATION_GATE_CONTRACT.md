# Stage 6 Final Integration Gate Contract (`STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md`)

Status: **STAGE 6.10 — BINDING CONTRACT**

This document defines the public contract for the Stage 6.10 final
integration gate / release gate / Stage 7 handoff. It is the authoritative
specification that `stage6_final_integration_gate.py` implements.

---

## 1. Purpose

Stage 6.10 is a **read-only certification layer** over the Stage 6 Control
Center integration foundation. It answers one question:

> Is the Stage 6 local Control Center real-integration foundation complete
> enough to close Stage 6 and safely hand off to Stage 7?

It is **not** new backend feature work, a Read API, frontend UI sync, a
WebSocket/SSE/polling server, a Next.js API route, a real AI dispatch, a
Buffer integration, cloud telemetry, or a SaaS feature.

---

## 2. Public function contract

```python
def run_stage6_final_integration_gate(
    *,
    repo_root,                       # local filesystem path; URL rejected
    checked_at: str,                 # caller-supplied timestamp; no clock used
    output_path=None,                # None => write nothing
    require_clean_git: bool = True,  # dirty working tree => blocker
    run_smoke: bool = True,          # run scripts/test_smoke.py
    run_security_scan: bool = True,  # run scripts/security_scan_baseline.py
    run_control_center_tests: bool = True,  # run pytest scos/control_center/tests
    run_frontend_checks: bool = False,       # pnpm lint/build (opt-in)
) -> Stage6FinalIntegrationResult | Stage6FinalIntegrationError
```

Rules:

- `checked_at` is caller-supplied. The gate never reads `datetime.now`,
  `time.time`, or any clock.
- `output_path=None` must not write any file.
- If `output_path` is provided, write deterministic JSON only (sorted keys,
  LF line endings, trailing newline).
- The gate must not mutate any Stage 6 artifact, DB, event, audit, queue,
  or approval store. The only write it may perform is the single report JSON
  at the caller-supplied `output_path`.
- Arbitrary command execution is forbidden. Subprocess use is limited to
  read-only `git` queries and running the existing approved smoke / security /
  pytest scripts (and optional `pnpm lint` / `pnpm build` from
  `apps/control-center`, never `pnpm install`).
- A blocker is never downgraded to a warning to achieve GO.

---

## 3. Result schema

`Stage6FinalIntegrationResult` (frozen, deterministic):

| field | type | notes |
|---|---|---|
| `ok` | bool | always `True` for the success envelope |
| `schema_version` | int | `1` |
| `accepted` | bool | `True` only on GO |
| `gate_id` | str | `s6g-` + 16 hex of SHA-256(`gate|checked_at|repo_root`) |
| `checked_at` | str | echoed caller input |
| `stage` | str | `"6.10"` |
| `stage_closed` | bool | `True` only on GO |
| `go_no_go` | str | `"GO"` or `"NO_GO"` |
| `readiness_level` | str | `"certified"` / `"blocked"` |
| `readiness_score` | int | 0..100 |
| `readiness_max_score` | int | `100` |
| `checks` | tuple[Stage6GateCheck, ...] | immutable per-check observations |
| `evidence` | tuple[Stage6GateEvidence, ...] | immutable read-only evidence records |
| `blockers` | tuple[Stage6GateBlocker, ...] | immutable named blockers |
| `stage7_handoff_items` | tuple[Stage7HandoffItem, ...] | immutable handoff items |
| `output_path` | str \| None | report path or `None` |
| `metadata` | FrozenMap | generator, flags, score breakdown |

Nested mappings/collections are immutable: `FrozenMap` stores mappings as a
sorted tuple of `(key, value)`; dataclass fields are `frozen`. Reassigning a
field or `FrozenMap.items` raises `AttributeError`/`TypeError`.

`Stage6FinalIntegrationError` is returned instead when preflight input
validation fails (missing repo, empty `checked_at`, URL path).

---

## 4. Scoring model

Deterministic, non-probabilistic. Bucket weights sum to 100:

| bucket | weight | covers |
|---|---|---|
| preflight | 5 | `validate_inputs`, `validate_repo_root_exists`, `validate_git_state` |
| source_contract | 35 | per-stage 6.2-6.9 + 6.10 artifact/doc presence |
| stage6_coherence | 15 | 6.7 audit wiring, 6.8 security scan CC+FE coverage + runnable |
| safety_boundary | 20 | no forbidden backend/frontend tokens, no real AI dispatch, subprocess allowlist, gate self-scan |
| stage7_handoff | 25 | handoff items generated, Stage 7 handoff doc exists |

Bands:

- `readiness_score == 100` **and** `blockers == []` => `GO`, `stage_closed=True`.
- Any `error`/`critical` blocker => score clamped to `≤ 79` and `NO_GO`.
- Only `warning` blockers => score in `80..99`, `NO_GO`.
- `GO` only when score is exactly 100 and there are zero blockers.

Optional run guards (`run_smoke`, `run_security_scan`, `run_control_center_tests`,
`run_frontend_checks`) are GO guards, not score contributors: on failure they
add a blocker; when skipped they are recorded as `skipped` and do not reduce
the score.

---

## 5. Blocker / warning rules

- A missing required Stage 6.2-6.10 artifact, test, spec doc, or cert doc is an
  **error** blocker.
- Missing Stage 6.10 contract/release/handoff docs are an **error** blocker.
- The 6.7 approval-audit ledger not wired into `command_runner.py` is an
  **error** blocker.
- The Stage 6.8 security scan lacking `scos/control_center` or
  `apps/control-center` coverage is an **error** blocker.
- Any forbidden backend/frontend token (network, real-AI, GUI/clipboard
  automation, WebSocket, SSE, polling, cloud storage, server actions) is a
  **critical** blocker.
- A dirty git working tree under `require_clean_git=True` is an **error**
  blocker.
- Blockers are never downgraded. Warnings alone do not close the stage.

---

## 6. `output_path` behavior

- `output_path=None` => no file written; `result.output_path is None`.
- `output_path="path/to/file.json"` => writes `file.json`.
- `output_path="path/to/dir"` => writes `path/to/dir/stage6_final_integration_report.json`.
- Output is stable JSON: `json.dumps(payload, sort_keys=True, indent=2)` +
  `"\n"`, written with `newline="\n"`. Re-running with identical inputs and
  `checked_at` produces byte-identical output.

---

## 7. Deterministic constraints

- Caller-supplied `checked_at` only.
- No `datetime.now`, `date.today`, `time.time`.
- No `random`, no `uuid`.
- Deterministic IDs use stable SHA-256 inputs (`gate`, `checked_at`, `repo_root`).
- Same local artifacts + same `checked_at` produce stable, identical output.
- Source/spec/cert/doc existence checks are filesystem-only; no network.

---

## 8. Forbidden behaviors (hard boundary)

The gate itself and the Stage 6 artifacts it inspects must never exhibit:

- network libraries or calls (`requests`, `urllib.request`, `http.client`,
  `socket`, `aiohttp`, `httpx`, `smtplib`, `websocket[s]`)
- real AI dispatch imports (`openai`, `anthropic`)
- GUI / clipboard automation (`selenium`, `playwright`, `pyautogui`,
  `pyperclip`, `win32clipboard`)
- `subprocess` outside the allowlisted modules
  (`command_runner.py`, `stage5_final_certification.py`,
  `stage6_final_integration_gate.py`)
- `os.system`, `shell=True`, `pty`
- frontend `fetch(`, `XMLHttpRequest`, `axios`, `WebSocket`, `EventSource`,
  `setInterval`, `setTimeout`, `Date.now`, `Math.random`, `crypto.randomUUID`,
  `localStorage`, `sessionStorage`, `"use server"`, `navigator.clipboard`
- Next.js `route.ts` / `middleware.ts` or `app/api` directories
- any cloud/SaaS/telemetry/integrations-buffer behavior
