# Super Creator OS — Production-Readiness Audit

**Question:** Is this project truly production-ready for **public deployment**?
**Verdict:** **No — not yet.** It is a strong, well-engineered **single-user, local, offline**
system. The bar it misses is *public/multi-user/operable* deployment.

**Reviewers' hats:** Principal Architect · Staff QA · DevOps · Security.
**Date:** 2026-06-23 · **Branch:** `master` @ `db2bf4f` · **Mode:** read-only (no code changed).
**Scope:** ~9.1k LOC Python across `integrations/{learning,highlight,shortgen,adapter,mcp,video-use}`.

---

## READINESS SCORE: **48 / 100**
> "Production-grade data spine; not yet a deployable product."

Two different bars are in play and must not be confused:
- **Single-user local tool:** ~70/100 — usable today by a developer on one machine.
- **Public deployment (the asked bar):** **48/100** — blocked by deployment, observability,
  docs, and concurrency gaps below.

| # | Dimension | Score | One-line basis |
|---|---|---:|---|
| 1 | Architecture | 70 | Clean additive boundaries; not scale/cloud-shaped (single-file DB, O(n²) append). |
| 2 | Code Quality | 74 | Good docstrings/validation; recently de-duped; minor dead code + broad excepts remain. |
| 3 | Testing | 55 | Learning layer excellent (57 checks); **0 tests** for MCP + video-use engine (~1.7k LOC). |
| 4 | Reliability | 58 | Local graceful-degradation exists; no systematic retry; integrity guard can wedge. |
| 5 | Memory System | 72 | Excellent integrity (atomic + tamper-evident + append-only + backup); **no concurrency control**. |
| 6 | Security | 58 | Secrets clean, no shell-injection; but MCP arbitrary FS, unpinned engine deps, indirect prompt-injection unhandled. |
| 7 | Deployment | 30 | **No Docker, no running CI, not cloud-native, Windows-centric.** |
| 8 | Observability | 22 | **No logging/metrics/monitoring/alerting** — 100 `print()`, 0 `logging`. |
| 9 | Documentation | 40 | No root README / install guide / LICENSE; rich *design* docs only. |

Weighted toward public-deployment criteria (Deployment + Observability + Docs gate operability),
the composite lands at **48**.

---

## BLOCKERS (P0 — must clear before any public deploy)

| ID | Blocker | Evidence | Why it blocks |
|---|---|---|---|
| **P0-1** | **No deployable artifact / containerization** | No `Dockerfile`, `compose`, or k8s anywhere; system deps (ffmpeg) assumed on PATH; `vu.py` is a Windows UTF-8 shim. | Cannot reproducibly stand the system up off the author's machine. |
| **P0-2** | **No LICENSE + no root README/install** | `ls README* LICENSE` at root → none (engine has its own LICENSE only). | No license = legally not redistributable/deployable as a public project; no onboarding path for a new user. |
| **P0-3** | **Observability is effectively zero** | `import logging` = 0 occurrences; `print()` = 100 in non-test code; no metrics/health/alerting. | A public service you cannot log, monitor, or alarm on is not operable in prod. |
| **P0-4** | **Memory has no concurrency control (lost-update race)** | `memory_writer.safe_append` ([memory_writer.py:90](integrations/learning/memory_writer.py:90)) does read→validate→write with **no file lock** (`grep fcntl/msvcrt/flock` = none). TOCTOU between `verify_db_integrity` and `os.replace`. | Atomic write prevents *corruption* but **two concurrent writers silently lose a record**. Any multi-user/multi-process deploy loses data. |
| **P0-5** | **CI exists but does not run** | `.github/workflows/ci.yml` present + registered "active", but `gh api .../actions/runs` → `total_count: 0`. Actions appears disabled on the repo. | The quality gate is theoretical; nothing actually blocks a bad push today. |

---

## RISKS (high-impact, not strictly blocking)

| ID | Risk | Evidence | Severity |
|---|---|---|---|
| **R-1 (P1)** | **MCP server = arbitrary file read/write** | `scos_video_mcp.py` tools take raw `path`/`out_path` strings and hand them to ffmpeg (`probe`, `trim`, `grade`, `extract_audio`, `concat_list` …). No path allow-listing/sandbox. **0 tests.** | localhost-stdio today (moderate); **P0 if ever exposed over network** — arbitrary host file read & overwrite. |
| **R-2 (P1)** | **Indirect prompt injection via ingested content** | Transcripts/EDLs → `render_to_memory` → `lesson_learned`/hooks in `database.json` → `recommendation_service` seeds → consumed by an LLM orchestrator. No sanitization of free-text fields. | Malicious caption/filename text can carry instructions resurfaced to the agent. |
| **R-3 (P1)** | **Engine deps unpinned + no vuln scanning** | `pyproject.toml`: `requests, librosa, matplotlib, pillow, numpy` — **no version pins, no lockfile**; no `pip-audit`/Dependabot. Root `requirements.txt` is pinned (good). | Non-reproducible builds; silent CVE intake on the heaviest dependency surface. |
| **R-4 (P1)** | **Untested high-complexity code** | `video-use/engine/helpers/render.py` (662 LOC), `timeline_view.py` (408), `grade.py` (380), and `scos_video_mcp.py` — **all 0 tests**. `adapter` now covered indirectly by e2e; `timeline_to_edl.py` still untested. | The most complex, side-effecting code is unverified. |
| **R-5 (P2)** | **Unbounded growth** | `_db_backups/`, `_telemetry_backups/`, `work/seeds/`, `events.jsonl` never pruned; DB is one JSON file, append re-loads + deep-compares whole array → **O(n²)**. | Disk bloat + slowdown over time (fine short-term, bad at scale). |
| **R-6 (P2)** | **Integrity guard can wedge** | If a crash lands between `_atomic_write_json` and `_write_marker` ([memory_writer.py:132-134](integrations/learning/memory_writer.py:132)), the sha256 marker is stale → every subsequent `safe_append`/read **fails closed** ("written outside safe_append") until manual repair. | Fail-closed is safe but creates a manual-recovery outage with no runbook. |
| **R-7 (P2)** | **Standing auto-delete of source media** | `CLAUDE.md` Raw-Cleanup protocol auto-deletes `input/reference/` after a job. | Operationally irreversible; if a precondition check is wrong, user source is gone. |
| **R-8 (P2)** | **Error-handling smells** | 15 broad `except` and ~10 `except: pass` in non-test code; possible dead `atomic_write_json` in `render_to_memory.py:319`. | Swallowed failures hide root causes; small drift risk. |
| **R-9 (P3)** | **Platform-coupling** | Windows-specific UTF-8 shim + font assumptions; cloud assumes none of this. | Portability friction for Linux/cloud runners. |

---

## FINDINGS BY AREA

### 1. Architecture — 70
- **Strengths:** Genuinely additive boundaries — the learning spine is **stdlib-only** (no deps),
  the video layer is isolated, the MCP server is a self-contained module, `video-use` is a
  vendored engine coupled only via files/`memory/`. Event-driven (`event_bus`). Clear single
  write path to `database.json`.
- **Weaknesses:** Not scale-shaped — one JSON-file system-of-record, O(n²) appends, local-FS
  assumptions. Largest files (`render.py` 662, `montage.py` 476, `dq_report.py` 596) are
  complexity hotspots. Technical debt is **known and tracked** (prior `project_audit/`, the just-closed
  P0/P1 items), which is itself a maturity signal.

### 2. Code Quality — 74
- Strong docstrings, schema validation, atomic writes, honest v1/v2/v3 scoping.
- Recent improvements this cycle: removed `eval()` (`scos_video_mcp`), de-duped v1 validation
  (single source of truth in `validators.py`).
- Remaining: ~15 broad excepts / ~10 `except: pass`; a likely-dead `atomic_write_json` in
  `render_to_memory.py`; `print()`-as-output instead of logging.

### 3. Testing — 55
- **Coverage map:** learning = 5 suites / **57 checks** (excellent: pos/neg/regression, e2e closed-loop,
  write-guard, tamper-evidence); highlight = 21; shortgen = 13 + skip-safe smoke. **Total ~207 checks.**
- **Gaps:** `mcp/` = 0 tests (security-sensitive), `video-use/` = 0 tests (~1.7k LOC),
  `timeline_to_edl.py` = 0. No coverage measurement, no property/mutation testing. The render
  smoke test **self-skips** without a clip, so the real render path is unproven in CI.

### 4. Reliability — 58
- **Good local patterns:** graceful degradation in `montage.py:139` (retry without zoom) and
  `short_generator.py:233` (retry without hook overlay); `vu.py` UTF-8 hardening.
- **Missing:** no systematic retry/backoff; no recovery for partial/failed renders; integrity
  guard fail-closed can wedge with no documented recovery (R-6). No health checks.

### 5. Memory System — 72
- **Best-in-repo:** validate-before-write, timestamped backup, **atomic** `os.replace`, append-only
  post-condition, dup guard, write-token gate, **tamper-evident sha256 marker** with read-time verify.
- **Blocking gap:** **no locking** → lost-update race (P0-4). **Unbounded backups** (R-5).
  Single-writer design is correct *today* but undeclared as a hard constraint.

### 6. Security — 58
- **Clean:** `.env` is **gitignored + untracked**, `.env.example` provided, **no hardcoded secrets**,
  **no `shell=True`/`os.system`/`pickle`**, all subprocess calls use list-form args.
- **Open:** MCP arbitrary-FS (R-1), indirect prompt injection (R-2), unpinned engine deps + no
  scanning (R-3), auto-delete protocol (R-7). No `SECURITY.md`, no threat model.

### 7. Deployment — 30
- **No** Dockerfile / compose / k8s / Procfile. **CI not running** (P0-5). Not cloud-native
  (stateful single-file DB, local FS, ffmpeg system dep). Windows-centric entrypoint.
  `.mcp.json` wires the server with a bare `python` command (no venv/abs-path pinning).

### 8. Observability — 22
- **None of the four pillars.** 0 structured logging (100 `print()`), no metrics, no monitoring,
  no alerting, no request/trace IDs, no health endpoint. `dq_report.py` (manual data-quality
  report) and `telemetry.json` (product metrics, not system metrics) are the closest artifacts —
  neither is operational telemetry.

### 9. Documentation — 40
- **Missing for users:** root `README.md`, install/quickstart guide, `LICENSE`, `CONTRIBUTING`,
  architecture overview for newcomers. `CLAUDE.md` is agent-config, not human onboarding.
- **Present (design-grade):** `DATA_ACCUMULATION_PHASE.md`, `DATA_INFRASTRUCTURE_PHASE.md`,
  `PROVENANCE_LAYER.md`, `DQ_REPORT_SYSTEM.md`, `workflow-map.md`, `integrations/README.md`,
  and a well-commented `requirements.txt`. Good DX seeds, no front door.

---

## RECOMMENDATIONS (classified)

### P0 — Deployment blockers
1. **Add a deploy artifact:** `Dockerfile` (python:3.11-slim + `apt install ffmpeg` + `pip install -r requirements.txt`) and document `docker run`. Pin `.mcp.json` to the venv interpreter + absolute script path.
2. **Add `LICENSE` + root `README.md`** (what it is, install, quickstart, the single `run all tests` command, the ffmpeg prerequisite). This also unblocks legal redistribution.
3. **Introduce structured logging** (`logging` with levels + JSON formatter), replacing `print()` in non-test modules; add a minimal health/self-check command. This is the floor for operability.
4. **Make memory single-writer explicit OR safe:** add an OS file lock (`msvcrt`/`fcntl` or `filelock`) around `safe_append`, *or* document and enforce single-writer and refuse concurrent invocation. Re-order to write the integrity marker inside the same critical section.
5. **Turn CI on:** enable Actions (repo Settings → Actions → General → Allow all), add `workflow_dispatch` for manual runs, and require it as a merge gate. A green-but-dormant workflow is not CI.

### P1 — Must fix before public release
6. **Sandbox the MCP server:** allow-list a working root and reject paths that escape it (`Path.resolve()` + prefix check) on every `path`/`out_path`; add the first MCP test suite.
7. **Sanitize ingested free-text** (`lesson_learned`, hooks, filenames) before it re-enters recommendations/agent context — strip/escape instruction-like content (indirect prompt-injection defense).
8. **Pin engine deps + add scanning:** lock `pyproject.toml` versions (or a lockfile); add `pip-audit` and Dependabot to CI.
9. **Test the untested complex code:** `render.py`, `timeline_view.py`, `grade.py`, `timeline_to_edl.py`, and the MCP tools; add a CI render smoke that ships a tiny fixture clip so the real path runs (not skip).
10. **Document memory recovery (R-6):** a runbook for "integrity guard tripped → rebuild marker".

### P2 — Should fix
11. **Bound growth:** keep-last-N pruning for `_db_backups/`, `_telemetry_backups/`, `work/seeds/`; size-rotate `events.jsonl`; make append O(1) amortized (validate only the new record at write).
12. **Tighten error handling:** replace broad `except`/`except: pass` with targeted handling + logged context; remove dead `atomic_write_json` in `render_to_memory.py`.
13. **Gate the auto-delete protocol** behind an explicit env flag (default off) for any non-author deployment.

### P3 — Optional
14. Coverage measurement + thresholds in CI; OS-aware font/path resolver to drop Windows coupling; calibration cache reuse; `SECURITY.md` + threat model.

---

## NEXT ACTIONS (ordered, smallest blast radius first)
1. **Enable Actions + add `workflow_dispatch`** (P0-5) — minutes; turns the existing suite into a real gate.
2. **Add `LICENSE` + root `README.md`** (P0-2) — unblocks onboarding & redistribution.
3. **`Dockerfile` + documented run** (P0-1) — first reproducible artifact; also fixes the CI render-fixture path.
4. **File lock around `safe_append`** (P0-4) — closes the lost-update race; small, well-bounded change.
5. **`logging` migration + health check** (P0-3) — the operability floor.
6. Then P1: MCP path allow-listing + first MCP tests (R-1), input sanitization (R-2), dep pinning + `pip-audit` (R-3).

**Bottom line:** the *trust core* (memory integrity, validation, learning closure) is genuinely
production-grade and well-tested. What stands between this and **public** deployment is not the
core — it's the **operational shell**: containerization, running CI, logging/monitoring,
concurrency safety, licensing/onboarding, and tests over the MCP + video engine. Clear the five
P0s and this moves from ~48 to a defensible public-beta posture.
```
```
*Read-only audit — no source files were modified. Deliverable: this file only.*
