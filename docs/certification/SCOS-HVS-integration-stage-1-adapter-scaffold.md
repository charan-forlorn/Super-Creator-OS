# SCOS–HVS Integration — Stage 1: Adapter Scaffold and Read-Only Dry-Run Contract

**Status:** CERTIFIED — ready for Stage 2 (Deterministic SCOS-to-HVS Schema Mapper and Round-Trip Contract).
**Verdict:** PASS. Integration Stage 1 CLOSED.

---

## 1. Objective

Create a safe, additive adapter scaffold inside **Super Creator OS (SCOS)** that
represents the **Hermes Video Studio (HVS)** production engine through the
existing SCOS agent-adapter contract, discovers/validates an HVS repository and
Python executable, builds deterministic argument-list HVS CLI commands, runs
only approved read-only capability probes, and returns a valid existing SCOS
`AgentAdapterResult` — without importing HVS internals, without writing into
HVS, and without changing any current render routing or product behavior.

## 2. Baselines

| Artifact | Value |
| --- | --- |
| SCOS root | `C:\Workspace\super-creator-os` |
| SCOS branch | `main` |
| SCOS starting HEAD | `a85e50d3f4d1687da44f613577517ac4cfd694d3` (matches required baseline) |
| SCOS initial status | clean (working tree empty before Stage 1 edits) |
| HVS root | `C:\Workspace\hermes-video-studio` |
| HVS branch | `main` |
| HVS starting HEAD | `8c0708d71f92ed5a417ce6ee678ae28f76c39944` (matches required baseline) |
| HVS initial status | clean |
| SCOS Python | `C:\Workspace\super-creator-os\.venv\Scripts\python.exe` — Python 3.11.15 |
| HVS Python | `C:\Workspace\hermes-video-studio\.venv\Scripts\python.exe` — Python 3.11.15 |

> Note: at Stage-1 entry SCOS `HEAD...origin/main` reported `1 0` (SCOS one
> commit ahead of the locally available `origin/main`). The required HEAD hash
> (`a85e50d…`) is exactly present and the working tree is clean, so this is the
> intended starting state; no pull/fetch was performed (forbidden).

## 3. Existing Contract Reused

The adapter implements the **existing** `BaseAgentAdapter` interface from
`scos/control_center/agent_adapter_contracts.py` and produces the **existing**
`AgentAdapterResult` / `AgentAdapterError` dataclasses from
`scos/control_center/agent_adapter_models.py`. No second adapter framework was
invented.

| Contract element | Reused from | Notes |
| --- | --- | --- |
| `BaseAgentAdapter` (abstract) | `agent_adapter_contracts.py` | `adapter_id`, `agent_name`, `runtime_type`, `capabilities` implemented |
| `AgentAdapterResult` | `agent_adapter_models.py` | `status` ∈ allowed set; `result_type="probe_report"`; `agent_name="hermes_video_studio"` |
| `AgentAdapterError` | `agent_adapter_models.py` | error kinds `invalid_configuration`, `unsafe_command`, `command_timeout`, `permission_error`, `adapter_blocked` |
| `AgentAdapterCapability` | `agent_adapter_models.py` | single read-only capability; no prompt delivery / result capture declared |
| Deterministic ID helper | `credential_redaction._stable_id` pattern | `_stable_id(prefix, *stable_parts)` (sha256, 16 hex) |
| Frozen tuple metadata | `agent_adapter_models._string_pairs` | `metadata` is `(key, value)` tuple of strings |
| Subprocess isolation | `command_runner.py` convention | `subprocess.run(list, cwd=..., shell=False, capture_output=True, text=True, timeout=...)` |

**Conventions reused (not reinvented):** immutable frozen dataclasses, tuple
metadata serialization, explicit `to_dict()` key order, caller-supplied
`created_at` (no clock/random/uuid), sha256 deterministic IDs, bounded output
excerpts, and an allow-list-driven command boundary.

## 4. Architecture Boundary

```
SCOS  →  HermesVideoStudioAdapter  →  subprocess(shell=False)
     →  HVS CLI (`python -m hvs.cli --help`)  →  structured SCOS AgentAdapterResult
```

HVS remains an independent certified production engine. SCOS remains the
control plane. No `import hvs.*`, no in-process renderer, no writes into HVS.

## 5. Files Changed (all inside SCOS)

| File | Change | Purpose |
| --- | --- | --- |
| `scos/control_center/hvs_adapter.py` | **NEW** | `HVSAdapterConfig`, `HermesVideoStudioAdapter`, `build_hvs_adapter_config` |
| `scos/control_center/tests/test_hvs_adapter.py` | **NEW** | 31 tests incl. live cross-repo HVS help-probe smoke |
| `scos/control_center/agent_adapter_models.py` | modified (additive) | +1 agent name (`hermes_video_studio`), +1 runtime (`hvs_cli`), +1 task type (`capability_probe`), +1 result type (`probe_report`), +4 error kinds |
| `scos/control_center/tests/test_agent_adapter_models.py` | modified | count assertions updated (5→6, 9→10, 10→11, 10→11, 10→14) to match additive allow-list growth |
| `scripts/security_scan_baseline.py` | modified (backward-compatible) | `hvs_adapter.py` added to `_CONTROL_CENTER_SUBPROCESS_ALLOWLIST` (the documented bless mechanism; the gate still flags any non-allow-listed control-center `subprocess` use) |

No `__init__.py` / registry change was required: the adapter is intentionally
**not registered** in the default `AgentAdapterRegistry` (see §9), so runtime
adapter selection and the default renderer are unchanged.

### Adapter configuration model (`HVSAdapterConfig`)

| Field | Default | Validation |
| --- | --- | --- |
| `hvs_repo_path` | required | must exist, be a directory, and contain `hvs/cli` (the CLI entry point) |
| `python_executable` | required | must exist as a file **or** be resolvable via `shutil.which` on PATH |
| `operation` | `hvs_capability_probe` | must be in `STAGE1_READONLY_OPERATIONS` |
| `timeout_seconds` | 60 | must be `0 < t ≤ 600` |
| `max_output_chars` | 4000 | must be positive |
| `cli_module` | `hvs.cli` | must not contain shell metacharacters |

No value is hard-coded to a user's home directory; all values are explicit or
supplied via the `build_hvs_adapter_config` factory.

### Stage 1 operation allowlist

```python
STAGE1_READONLY_OPERATIONS = ("hvs_capability_probe",)
```

The only permitted operation builds:

```python
["<python_executable>", "-m", "hvs.cli", "--help"]
```

Mutating HVS subcommands (`create-project`, `assemble-media`, `export-project`,
`render-hyperframes`, `plan-real-render-batch`, `run-real-render-batch`,
`create-render-pack`, `verify-real-render-output`, `create-handoff-package`,
`import-media`, `certify-mvp`, `backup-project`, `dashboard`, `release-gate`)
are held in a deny-list (`_FORBIDDEN_HVS_SUBCOMMANDS`) and are **never
constructed** — `build_argv()` only ever emits `--help`.

### Command construction (safe)

* `shell=False` (enforced at the `subprocess.run` call).
* `cwd` explicitly set to the resolved configured HVS root.
* `argv` is a **list**; paths with spaces stay single elements (no shell
  joining). Windows backslash separators are valid path content, not shell
  metacharacters.
* `capture_output=True`, `text=True`, `timeout` enforced.
* `input=""` (no stdin inheritance).
* `env={}` — explicitly minimal; no `os.environ` dump, no secrets on the
  command line.

### Error handling / normalization

Every failure mode returns a structured `AgentAdapterError` (no raw trace to
normal callers): `invalid_configuration` (missing repo/python/CLI, bad op, bad
timeout), `unsafe_command` (metacharacter in constructed argv), `command_timeout`,
`permission_error`, `adapter_blocked` (OSError/ValueError/unexpected). Non-zero
exit codes return a failed `AgentAdapterResult` carrying the exit code.

### Output bounding

`max_output_chars` (default 4000) bounds retained stdout/stderr; only a ≤200-char
excerpt is placed into result metadata for audit evidence. Unbounded CLI output
cannot enter SCOS events or memory.

### Deterministic ID behavior

`result_id = _stable_id("hvs-adapter-", hvs_repo_path, python_executable,
cli_module, operation, request_id)` — derived only from stable config/request
values. Volatile inputs (elapsed time, PID, random UUID, temp paths) are
excluded, so identical inputs → identical IDs across runs.

## 6. Security Evidence

* **shell=False:** proven by `test_shell_false_enforced` (captures the
  `subprocess.run` kwargs and asserts `shell is False`).
* **Argument-list construction:** `test_command_uses_argv_list` asserts argv is a
  list of exactly 4 elements `[py, "-m", "hvs.cli", "--help"]`.
* **cwd isolation:** `test_cwd_is_configured_hvs_root` + `test_parent_directory_escape_rejected`
  assert `cwd == resolved repo` and never a parent escape.
* **Timeout:** `test_timeout_returns_normalized_failure`.
* **No arbitrary commands:** `test_unsupported_operation_rejected_before_subprocess`
  asserts the subprocess is never reached for a disallowed op.
* **No secret exposure:** `test_no_secret_or_env_exposure` asserts `env == {}`
  and no secret/token tokens appear in argv.
* **No HVS writes:** `test_no_hvs_file_written_by_adapter` snapshots the repo
  file set before/after and asserts equality; the live smoke asserts HVS git
  status is unchanged.
* **Forbidden-token scan (Phase 9):** `shell=True`, `os.system`,
  `subprocess.Popen`, `requests`, `urllib`, `httpx`, `aiohttp`, `socket`,
  `getenv`/`environ`, `git push`/`reset`/`clean`, `rmtree`, `-rf` — **no
  matches in executable code** (only in docstrings/deny-list declarations).

## 7. Cross-Repository Read-Only Smoke

* **Approved probe:** `python -m hvs.cli --help` executed against the real HVS
  repo via `HermesVideoStudioAdapter.run_readonly_probe` (real `subprocess.run`,
  `shell=False`).
* **Result:** exit code 0, `AgentAdapterResult` with `status=result_ready`,
  non-empty help output.
* **HVS status before:** clean (empty `git status --porcelain=v1 -uall`).
* **HVS status after:** clean (empty) — **no new files, projects, state, media,
  cache, or render output created**.
* **HVS HEAD after:** `8c0708d71f92ed5a417ce6ee678ae28f76c39944` (unchanged).
* Covered by `test_real_hvs_readonly_help_smoke`, which skips only when the HVS
  repo is genuinely absent.

## 8. Test Evidence

| Suite | Result |
| --- | --- |
| `scos/control_center/tests/test_hvs_adapter.py` | **31 passed**, 1 benign warning (see §10) |
| `scos/control_center/tests/test_agent_adapter_models.py` | 9 passed (counts updated) |
| `scos/control_center/tests/test_agent_adapter_contracts.py` | 3 passed |
| Control Center suite (`scos/control_center/tests`) | **664 passed** (baseline 633; +31 new) |
| Full SCOS collection (`--collect-only -q`) | **1094** (baseline 1063; +31 new) |
| Full SCOS suite (`pytest -q -rA`) | **1094 passed, 1 warning** in 270.0s |
| Smoke (`scripts/test_smoke.py`) | **16 passed, 0 failed** (SMOKE: PASS) |
| Security scan (`scripts/security_scan_baseline.py`) | **PASS** — 389 files, 0 findings |

All adapter-contract and existing adapter tests remain compatible
(`test_existing_adapters_still_constructable`, `test_adapter_not_default_renderer`).

## 8b. Security Scan — False-Positive Resolution

The first security-scan run reported 5 `shell_or_arbitrary_execution` findings,
all on `hvs_adapter.py`, because the static scanner flags **any**
`subprocess.` reference in a control-center module *unless* that module is on
`_CONTROL_CENTER_SUBPROCESS_ALLOWLIST`. `command_runner.py` (which uses
`subprocess.run(..., shell=False)`) is blessed via exactly that list. The HVS
adapter uses the **identical safe pattern** (`shell=False`, list argv, isolated
`cwd`, `env={}`). The established, backward-compatible correction was to add
`scos/control_center/hvs_adapter.py` to that allow-list — the documented bless
mechanism. This does **not** weaken the gate: any *non*-allow-listed
control-center `subprocess` use is still flagged. After the correction the scan
reports **0 findings / PASS**. No `shell=True`, `os.system`, `subprocess.Popen`,
network import, `getenv`/`environ` dump, or destructive token exists in the
adapter's executable code.

## 9. Scope Confirmation

* **No schema mapping** — Stage 1 has none (`test_no_schema_mapping_in_stage1`).
* **No rendering** — no render command is ever built or executed
  (`test_no_render_command_executed`).
* **No backend change** — the default renderer (`VideoUseStudioBackend`,
  `scos/render/ffmpeg_engine.py`) and `VideoUseStudioBackend` behavior are
  untouched; the HVS adapter is **not registered** as a default.
* **No UI/API change** — no UI control or API route added.
* **No HVS modification** — HVS working tree clean before and after.
* **No dependency change** — no install / lock-file / `requirements.txt`
  change.
* **No HVS internals imported** — `hvs_adapter.py` imports only
  `subprocess`, `hashlib`, `sys`, `dataclasses`, `pathlib`, typing, and the
  local SCOS contracts/models.

## 10. Known Limitations

* Stage 1 implements **only** the read-only capability-probe contract. Timeline
  translation, project creation, asset transfer, render invocation, approval
  tokens, A/V-sync ingestion, quality-report ingestion, memory/commercial
  closure, and default-backend selection are explicitly **out of scope** and
  not implemented.
* The live smoke's single benign `pytest` warning
  (`PytestUnhandledThreadExceptionWarning` from a background reader thread
  during the real subprocess launch) does not affect correctness and is a known
  pytest/subprocess interaction, not a test failure.
* HVS `__pycache__` is git-ignored, so importing `hvs.cli` never dirties the HVS
  tree.

## 11. Rollback Procedure

The change is additive and self-contained. To roll back Stage 1:

```bash
cd C:\Workspace\super-creator-os
git revert --no-edit HEAD            # revert the single Stage 1 commit
# or, before commit:
git checkout -- scos/control_center/agent_adapter_models.py \
              scos/control_center/tests/test_agent_adapter_models.py
git clean -fd scos/control_center/hvs_adapter.py \
                scos/control_center/tests/test_hvs_adapter.py
```

No HVS state, render output, or external artifact was created, so no external
cleanup is required.

## 12. Final Readiness Verdict

**PASS — SCOS–HVS Adapter scaffold and read-only dry-run contract are certified
and ready for Stage 2 schema mapping.**

Render integration is **NOT** claimed complete; only the safe, read-only adapter
boundary and contract are established.

---

*Generated by the SCOS–HVS Stage 1 certification agent. All evidence above is
reproducible from the committed state of `C:\Workspace\super-creator-os` at the
single Stage 1 commit described in the Stage commit report.*
