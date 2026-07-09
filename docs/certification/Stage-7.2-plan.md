# Stage 7.2 Plan - Read Surface Contract and Coherence Gate

Predecessor: Stage 7.1, confirmed at commit
`b4d5d229df07f666c41181464a18a5d534262254`.

## 1. Goal

Add a deterministic contract and coherence gate proving that the Stage 7.1
read surface is read-only, deterministic, schema/contract aligned, coherent
with Stage 6 source artifacts, and safe for later Stage 7.3/7.4 read models
and UI projection.

## 2. Scope

Allowed Python files:

- `scos/control_center/read_surface_coherence_models.py`
- `scos/control_center/read_surface_coherence_gate.py`
- `scos/control_center/tests/test_read_surface_coherence_models.py`
- `scos/control_center/tests/test_read_surface_coherence_gate.py`
- `scos/control_center/__init__.py` only for lazy Stage 7.2 exports

Allowed docs:

- `docs/specification/READ_SURFACE_COHERENCE_GATE_CONTRACT.md`
- `docs/certification/Stage-7.2-plan.md`

Allowed contract references:

- `docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md`
- `docs/specification/STAGE7_READ_ONLY_QUERY_BOUNDARY.md`

## 3. Non-goals

- No new read capability beyond Stage 7.1.
- No frontend UI.
- No Next.js or localhost route.
- No WebSocket, SSE, polling, timer, or background worker.
- No command execution.
- No SQLite write.
- No JSONL append/write.
- No output file creation.
- No schema migration.
- No real adapter dispatch.
- No cloud, network, SaaS, payment, CRM, telemetry, or customer portal.
- No package/dependency changes.
- No Stage 4, Stage 5, Stage 6, or Stage 7.1 public contract breaks.
- No commit, push, tag, or release.

## 4. Test plan

Targeted tests:

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_coherence_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_coherence_gate.py -q
```

Stage 7.1 regression:

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_validation.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_query.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_snapshot.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_facade.py -q
```

Broader checks:

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_release.py
```

Use `--basetemp work/pytest-tmp/...` when the default user temp directory is
not accessible.

## 5. Acceptance criteria

- Preflight passes on `main`, `HEAD == origin/main`, clean tree, latest Stage
  7.1 commit.
- Stage 7.1 public exports remain intact.
- Stage 7.1 contract/certification artifacts are present.
- Required Stage 6 sources are compared to read surface output.
- Missing optional runtime artifacts produce warnings.
- Missing required artifacts produce blockers.
- Non-mutation checks compare known artifact hashes before and after the
  coherence query.
- Outputs are deterministic for identical local inputs and `checked_at`.
- No forbidden transport, UI, command execution, adapter, cloud, package, or
  store mutation behavior is introduced.

## 6. Would-be commit message

```
test(control-center): add Stage 7.2 read surface coherence gate
```
