# SCOS CI Operations Runbook

Operator-grade reference for the Super-Creator-OS (SCOS) continuous-integration
system. This runbook **explains** the certified CI behavior; it does **not**
override the executable configuration. When this document and the executable
source disagree, the source is authoritative.

- Authoritative remote-CI configuration: `.github/workflows/ci.yml`
- Authoritative local-parity tool: `scripts/ci_local_verify.py`
- Canonical interpreter (Windows): `.venv/Scripts/python.exe`
- Canonical repository root (example): `C:/Workspace/super-creator-os`

> All executable facts below were extracted directly from the committed blobs at
> the Cohort 8 certified HEAD `bf477536e379012f41a7e91fe8056e5d4eed63a1`
> (`scripts/ci_local_verify.py` blob `b40c4ac2…`, `ci.yml` blob
> `e685909b…`). Behavioral contract is additionally proven by the committed
> focused test `scripts/tests/test_ci_local_verify.py`.

---

## A. Purpose and Authority

The CI protects the repository from:

- regressions in the product test populations (Standard and Explicit Integration);
- import/API breakage (smoke gate);
- introduction of credential, payment-processor, network-exfiltration, or
  private-key patterns (static security-scan baseline);
- silent weakening of warning-as-error guards and cache isolation.

| Concern                          | Authoritative file                         |
| -------------------------------- | ------------------------------------------ |
| Remote CI trigger + gate order   | `.github/workflows/ci.yml`                 |
| Local CI-parity reproduction     | `scripts/ci_local_verify.py`               |
| Marker / population selection    | `ci.yml` (and `pytest.ini` `addopts`)      |
| Runbook (this document)          | `docs/runbooks/SCOS-CI-operations.md`      |

The runbook is the operator-facing explanation. Edits to CI behavior belong in
`ci.yml` / `ci_local_verify.py` via a separate, scoped change — never in this
document alone.

---

## B. Trigger Matrix

CI runs on the GitHub-hosted `ubuntu-latest` runner. All triggers target the
`main` branch only.

| Event              | Branch/filter        | Result                                                       |
| ------------------ | -------------------- | ------------------------------------------------------------ |
| `push`             | `main`               | Full gate sequence runs (smoke → security → Standard → Integration) |
| `pull_request`     | `main`               | Full gate sequence runs on the PR merge-ref                 |
| `workflow_dispatch`| (manual button)      | Full gate sequence runs (bootstraps first run / ad-hoc)     |

CI uses `concurrency` group `ci-${{ github.ref }}` with
`cancel-in-progress: true`: a newer push to the same ref cancels the in-flight
run.

---

## C. Gate Order

The GitHub-hosted job performs four setup steps (`actions/checkout@v4`,
`setup-python@v5` → 3.11, `apt-get install ffmpeg`, `pip install -r
requirements.txt`) and then the four fail-closed verification gates below, in
this exact order. The local verifier reproduces the **four verification gates
only** (it assumes the checkout/python/ffmpeg/pip setup is satisfied by the
operator environment) and runs them in the same order with the same commands.

| # | Gate                     | Purpose                                              | Canonical command shape                                                                                         | Success condition                              | Failure condition                                  | Expected evidence                              |
| - | ------------------------ | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------- | ---------------------------------------------- |
| 1 | Smoke                    | Fast import / API sanity for the local operator.    | `python scripts/test_smoke.py`                                                                                  | exit 0, prints `PASS` lines                    | non-zero exit (1)                                  | deterministic `PASS` output                    |
| 2 | Security scan baseline   | Static scan for credential/token/payment/network/private-key patterns in source only (docs not scanned). | `python scripts/security_scan_baseline.py`                                                          | exit 0, 0 findings                             | exit 1 on any finding                              | "0 findings" summary, redacted samples only    |
| 3 | Standard population      | Full product/unit/integration-excluded suite.       | `python -m pytest integrations scos scripts -m "not integration" -o cache_dir=<temp>/cache --basetemp <temp>/basetemp -W error::pytest.PytestConfigWarning -W error::pytest.PytestUnhandledThreadExceptionWarning -q` | exit 0, 0 failed, 0 error, 0 warning  | any non-zero exit; propagates child exit code     | summary line (passed / deselected / skipped)   |
| 4 | Explicit Integration population | Real-HVS / real-network acceptance tests (certified hermetic HVS double). | same as #3 but `-m integration` | exit 0, 0 failed, 0 error, 0 warning  | any non-zero exit; propagates child exit code     | summary line (passed / skipped)               |

Behavior on the first non-zero gate exit: the run stops at that gate; its exact
exit code is propagated; no later gate runs. Evidence (run logs, summary lines)
persists for audit.

---

## D. Certified Populations

`pytest.ini` declares `testpaths = integrations scos scripts`,
`norecursedirs` includes `work`, and `addopts = -m "not integration"` for
default collection. CI explicitly selects populations with marker expressions.

### Standard population

- Marker selection (explicit, authoritative): `-m "not integration"`.
- Collects everything **except** tests marked `@pytest.mark.integration`.
- The `integration` marker is documented in `pytest.ini` as "real-HVS /
  real-network acceptance tests; skipped by default collection".
- Expected deselection relationship: the Explicit Integration population is the
  exact complementary set selected by `-m integration`.
- Warning guards applied to **both** populations (see §G).
- Known classified skips are intentional (integration tests deselected by the
  Standard marker); they are not failures.

### Explicit Integration population

- Marker selection (explicit, authoritative): `-m integration`.
- Contains the real-HVS / real-network acceptance tests, certified hermetic via
  a temporary HVS double (no production HVS mutation).
- Run as a **separate** gate from Standard; the two must never be merged into a
  single command.

**Prohibition:** silently changing marker selection (e.g. `-m "not
integration"` → `-m "not integration and not slow"`, or swapping to `-m
"integration and not slow"`) invalidates the certified contract and the derived
parity tests. Any marker/selection change must be a single, explicitly reviewed
change that updates `ci.yml`, `ci_local_verify.py`, the parity tests, and this
runbook together.

**Reference counts (last certified — Cohort 8C, 2026-07-16):**

- Standard: `2603 passed / 3 classified skips / 21 deselected`
- Explicit Integration: `21 passed / 0 skipped`

These are **historical reference evidence**, not permanent hard-coded future
invariants. New code or tests legitimately change counts; the contract that must
hold is the *selection method and gate order*, not the absolute numbers.

---

## E. Local Parity Execution

`scripts/ci_local_verify.py` is a deterministic, read-only (except verifier-owned
OS-temp) local reproduction of the four CI verification gates.

**Canonical operator command (Windows):**

```powershell
cd C:\Workspace\super-creator-os
.venv\Scripts\python.exe scripts\ci_local_verify.py
```

Read-only inspection (no execution) — prints the constructed contract:

```powershell
.venv\Scripts\python.exe scripts\ci_local_verify.py --plan
```

Optional cleanup of verifier-owned temp after a green run:

```powershell
.venv\Scripts\python.exe scripts\ci_local_verify.py --clean
```

Properties:

- **Working directory:** the SCOS repository root (auto-detected as two levels
  above `scripts/ci_local_verify.py`; refuses to run against a different repo
  layout).
- **Canonical interpreter:** `.venv/Scripts/python.exe` (Windows). The verifier
  raises `EXIT_VERIFIER_ERROR` (2) at preflight if it is absent.
- **Process-local media environment:** before pytest gates the verifier copies
  the current environment, prepends a media-bin directory to `PATH` (never
  replaces it), and exports `SCOS_FFMPEG_BIN` / `SCOS_FFPROBE_BIN`. The real
  process environment is **not** mutated.
- **Unique run root:** each invocation creates a unique OS-temp directory
  `scos-ci-local-<UTC-stamp>-<pid>` (under `tempfile.gettempdir()`); never
  inside the repository.
- **Per-gate isolation:** each pytest gate gets its own unique `cache_dir` and
  `basetemp` under the run root (e.g. `<run-root>/standard/cache`,
  `<run-root>/standard/basetemp`, `<run-root>/integration/cache`,
  `<run-root>/integration/basetemp`).
- **cacheprovider:** enabled (the verifier never passes `-p no:cacheprovider`).
- **Exit-code interpretation:** `0` = all gates passed; the exact non-zero child
  exit code is propagated on first gate failure; `2` = verifier preflight error
  (missing interpreter or unresolved media binaries); `130` = interrupted.
- **Final success marker:** `RESULT: ALL GATES PASS` (followed by
  `RESULT: OVERALL PASS`).

> On Windows, pytest creates only the basetemp **leaf**; the verifier therefore
> provisions the parent directory chain before launching each pytest gate (the
> local equivalent of the CI `runner.temp` setup). This is the prerequisite for
> the §J startup-race handling.

---

## F. Media-Toolchain Preflight

- **Requirement:** `ffmpeg` **and** `ffprobe` must be resolvable and return exit
  0 from `-version`.
- **Resolution / verification:** the verifier checks each binary file exists and
  runs `<binary> -version`; if either fails, preflight aborts with
  `RESULT: GATE preflight FAIL (media precondition)` and verifier exit 2 — no
  pytest gate runs.
- **Approved handling:** PATH is **prepended** with the media-bin directory and
  `SCOS_FFMPEG_BIN` / `SCOS_FFPROBE_BIN` are exported into the **child** process
  environment only. This is process-local and reversible; the machine `PATH` is
  unchanged after the run.
- **Prohibited:** any permanent `PATH` mutation (user or system) during
  verification. Install media tools via the environment's own package manager
  (e.g. `scoop install ffmpeg`) outside of the verification command.
- **Environment-specific example:** on the canonical Windows operator machine
  the resolved shim dir is `C:/Users/chara/scoop/shims` (captured in
  `ci_local_verify.py` `_MEDIA_SHIM_DIR`); treat this as a machine-specific
  example, not a universal requirement.

---

## G. Warning Policy

Both populations apply exactly these two warning-as-error guards (never a
blanket `-W error`):

```text
-W error::pytest.PytestConfigWarning
-W error::pytest.PytestUnhandledThreadExceptionWarning
```

- A `PytestConfigWarning` as error catches misconfiguration (e.g. bad marker /
  cache setup).
- A `PytestUnhandledThreadExceptionWarning` as error catches background-thread
  exceptions that would otherwise pass silently.

**Invalidating parity:** using `--disable-warnings`, removing either guard,
adding a blanket `-W error`, or otherwise suppressing warnings breaks the
certified contract and the parity tests. The CI workflow and the local verifier
apply the identical two guards.

---

## H. Cache and Temporary-State Policy

- The pytest **cacheprovider stays enabled**; `-p no:cacheprovider` is never
  used (parity test asserts this).
- Cache (`cache_dir`) and `basetemp` use **unique OS-temp locations** outside
  the repository, one set per gate, under a unique run root per invocation.
- Two runs must **never share** the same temp roots.
- **Repository-local cache leakage is not acceptable:** the verifier's caches
  live under `tempfile.gettempdir()`, not under the repo. (`pytest.ini`'s
  project `cache_dir = scos/work/.pytest_cache` is the *default* collection
  cache; the CI/verifier override it with OS-temp paths via `-o cache_dir`.)
- Only **verifier-owned** temp state (the `scos-ci-local-*` run root) may be
  cleaned — and only with `--clean` after a green run, or the §J controlled
  stale-leaf removal.

---

## I. Failure Handling

1. **Preserve** the failing run-root (do not `--clean` on failure).
2. **Record** the first failing gate id and its exact exit code.
3. **Do not** immediately rerun the whole suite; reproduce the smallest relevant
   node or gate.
4. **Reproduce smallest:** run the single pytest node (`-m` + path/node id) or a
   single gate via the verifier rather than the full population.
5. **Classify** the failure: code (product bug), test (fixture/assertion defect),
   environment (missing dep/PATH), media (ffmpeg/ffprobe unresolved), or Windows
   basetemp startup race (see §J).
6. **Never** weaken a gate (remove warning guard, add skip/xfail, alter marker)
   to obtain green output.
7. **Repair cohort:** if the fix requires changing `ci.yml`,
   `ci_local_verify.py`, the scanner, the media resolver, an adapter, or
   authorization logic, open a **separately scoped repair cohort** — do not patch
   CI inside an unrelated task.

---

## J. Windows basetemp Startup Race

Diagnose a basetemp startup failure as follows:

- **Distinguish** a failure *before* test execution (e.g. `FileNotFoundError` /
  `PermissionError` / `OSError` while creating `basetemp`, or pytest reporting it
  could not set up the session) from a genuine **test failure** (a collected test
  asserting and failing). A startup race is a setup-phase error, not a red test.
- **Verify the signature:** the error references the basetemp path / directory
  creation, occurs before any test result, and typically clears on a clean
  unique temp root.
- **Remove only the verifier-owned stale leaf** when safe: delete the specific
  `scos-ci-local-*` run-root (or its stale `basetemp` leaf) that the verifier
  created — never repository files, never another process's temp, never user
  data.
- **Allow one evidence-backed retry** with a fresh unique run root. The verifier
  already creates a unique run root per invocation, so a rerun naturally uses a
  new temp.
- **Never retry indefinitely.** After more than one clean retry fails with the
  same signature, stop and open a repair cohort.
- **Do not** classify a startup race as product-certification success. A clean,
  **completed** run (all four gates reaching `RESULT: ALL GATES PASS`) is required
  for certification; a run that only avoided the race without completing is not
  proof of product health.

---

## K. Change-Maintenance Checklist

Any future change to `ci.yml` or `ci_local_verify.py` must, in the **same**
change boundary, update and verify:

- triggers (§B);
- gate order (§C);
- marker expressions (§D);
- warning guards (§G);
- cache contract (§H);
- media preflight (§F);
- success markers (§E / `RESULT: ALL GATES PASS`);
- parity tests (`scripts/tests/test_ci_local_verify.py`);
- this runbook (§A–§M).

CI/local parity must remain a **single change boundary**: the remote workflow and
the local verifier are never allowed to drift apart.

---

## L. Prohibited Shortcuts

The following are incompatible with the certified contract and must not be used
to "fix" a run:

```text
-x                          # stops after first failure only / hides scope
--maxfail                   # caps failure reporting, hides real scope
--disable-warnings          # defeats warning-as-error guards (§G)
warning ignores             # any -W ignore / filterwarnings override
manual test exclusions      # ad-hoc -k / --ignore not in the certified contract
altered marker expressions  # any change to -m "not integration" / -m integration
-p no:cacheprovider         # disables cacheprovider (§H) — parity test forbids it
parallel authoritative pytest  # the canonical run is single-process, sequential
global Python               # must use .venv/Scripts/python.exe, not system python
persistent PATH changes     # media env is process-local only (§F)
fabricated success markers  # never hand-edit RESULT: ALL GATES PASS
```

---

## M. Reference Results (last certified — Cohort 8C, 2026-07-16)

Historical reference evidence tied to the certified HEAD
`bf477536e379012f41a7e91fe8056e5d4eed63a1`. Treat as a snapshot, not a permanent
contract.

```text
CI/local semantic parity : PASS
Focused parity tests      : 27 passed
Authoritative local verifier : exit 0
Final verifier marker     : RESULT: ALL GATES PASS
Smoke                     : PASS
Security scan             : exit 0 / 0 findings
Standard population       : 2603 passed / 3 classified skips / 21 deselected
Explicit Integration      : 21 passed / 0 skipped
Warning guards            : PASS (0 warning-guard violations)
```

Re-certification reuses these as a baseline; absolute counts may shift as the
codebase evolves, but the gate order, markers, warning guards, and cache/isolation
contract must remain unchanged unless updated through the §K checklist.
