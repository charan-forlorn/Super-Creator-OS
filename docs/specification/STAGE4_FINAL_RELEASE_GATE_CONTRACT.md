# Stage 4 Final Release Gate Contract (Stage 4.19)

Schema version: `STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION = 1`
Module: `scos/commercial/stage4_final_release_gate.py`
Models: `scos/commercial/release_gate_models.py`

## Purpose

The Stage 4 final release gate is the local-only certification layer that
answers one question:

> Is Stage 4 complete, commercially coherent, locally verifiable,
> security-baselined, and ready for Stage 5 execution planning?

It inspects the Stage 4.1–4.18 commercial foundation (contract docs,
executable source, Stage 4.18 hardening assets), optionally runs the approved
local verification scripts, and produces a deterministic readiness score, a
GO / CONDITIONAL_GO / NO_GO verdict, and the Stage 5 handoff items.

## Non-goals

- It does not rebuild reports or delivery packages.
- It does not run outreach, generate customer messages, or send anything.
- It does not implement CRM, payment, billing, invoice generation, SaaS,
  dashboards, API servers, databases, WebSockets, polling, agent dispatch,
  cloud storage, or LLM calls — and it verifies executable source does not
  either.
- It does not mutate any Stage 4.1–4.18 artifact. Its only write is the
  single gate-report JSON at the caller-supplied `output_path`.
- It does not commit, push, tag, or run any mutating git command.

## Public API

```python
from scos.commercial import run_stage4_final_release_gate

run_stage4_final_release_gate(
    *,
    repo_root,                      # str | pathlib.Path, must exist, local only
    checked_at: str,                # caller-supplied timestamp string (no real clock)
    output_path=None,               # str | pathlib.Path | None, local only
    require_clean_git: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_release_script: bool = False,
    allow_warnings: bool = True,
) -> Stage4FinalReleaseGateResult | Stage4FinalReleaseGateError
```

Expected failures return `Stage4FinalReleaseGateError`; the function does not
raise for them. `http://` and `https://` values are rejected for both paths.

## Model contracts

All models are frozen dataclasses with `of(...)` factories (where useful) and
`to_dict()` serialization. `metadata` is always a `FrozenMap`
(`scos/commercial/report_models.py`); no mutable dict/list is exposed.

- `Stage4ReleaseCheck`: `check_name`, `status` (success/failure/skipped),
  `severity` (info/warning/error/critical), `category`, `artifact_path`,
  `error_kind`, `error_detail`, `metadata`.
- `Stage4ReleaseBlocker`: `blocker_id`, `category`, `severity`
  (warning/error/critical), `title`, `detail`, `recommended_action`,
  `source_check`, `metadata`.
- `Stage5HandoffItem`: `item_id`, `title`, `category`, `priority`
  (low/normal/high/urgent), `description`, `stage5_owner`,
  `source_stage4_evidence`, `metadata`.
- `Stage4FinalReleaseGateResult`: `ok`, `schema_version`, `accepted`,
  `release_gate_id`, `checked_at`, `stage`, `stage_closed`, `go_no_go`,
  `readiness_level`, `readiness_score`, `readiness_max_score`, `checks`,
  `blockers`, `stage5_handoff_items`, `output_path`, `metadata`.
- `Stage4FinalReleaseGateError`: `ok=False`, `schema_version`, `error_kind`,
  `error_detail`, `failed_check`, `checks`, `blockers`, `metadata`.

Check categories in use: `preflight`, `source_contract`,
`commercial_pipeline`, `hardening_foundation`, `testing`, `security`,
`release_readiness`, `stage5_handoff`.

## Release gate ID

Derived deterministically — no uuid, no random, no clock:

```
sha256(checked_at | <repo_root resolved name> | stage4-final-commercial-release-gate)[:12]
id = "stage4-final-commercial-release-gate-<sanitized repo name>-<sanitized checked_at>-<digest>"
```

## Release gate flow and required checks

```
validate_inputs
  -> validate_git_state              (read-only git, subprocess exception)
  -> validate_stage4_contract_files  (19 contract docs, label->path mapping in metadata)
  -> validate_commercial_source_files (20 executable sources, mapping in metadata)
  -> validate_hardening_foundation   (10 Stage 4.18 assets)
  -> validate_no_stage4_20           (stage-over-fragmentation scan)
  -> run_smoke_script                (optional flag, default on)
  -> run_security_scan_baseline      (optional flag, default on)
  -> run_release_script              (optional flag, default OFF)
  -> validate_static_forbidden_behavior (import-level scan of executable source)
  -> validate_stage5_handoff_readiness  (handoff doc + 10 deterministic items)
  -> compute_readiness               (score + GO/NO-GO verdict)
  -> write output JSON               (only if output_path given, only on the result path)
```

### validate_git_state

Runs only read-only git queries: `git status --short --untracked-files=all`,
`git rev-parse HEAD`, `git rev-parse origin/main`,
`git branch --show-current`. Policy: branch must be `main`, HEAD must equal
`origin/main`, and the working tree must be clean. Any violation records a
**critical** blocker (the gate still completes and reports NO_GO). If the git
binary is unavailable while `require_clean_git=True`, the gate returns a
deterministic `GIT_UNAVAILABLE` error. With `require_clean_git=False` the
check is recorded as `skipped` with severity `info` — an explicit operator
waiver that costs half of the git score bucket but does not count as a
warning.

**Subprocess exception.** Production commercial modules are subprocess-free
by convention. This gate is the single documented exception: `subprocess` is
allowed here only for the read-only git queries above and the approved local
scripts (`scripts/test_smoke.py`, `scripts/security_scan_baseline.py`,
`scripts/test_release.py`). Nothing else may use it.

### validate_no_stage4_20

Scans only `docs/certification/` and `docs/specification/` (filenames plus
`.md` content) for `Stage-4.20` / `Stage 4.20` and later markers, which must not appear.
Filename matches always produce the `STAGE_OVER_FRAGMENTATION` critical
blocker. Content matches on negation / non-goal lines (containing "no",
"not", "never", "forbid", "refuse", "do not", "must not", or "non-goal") are
allowed: documenting the rule that no Stage 4.20+ may exist is not a
violation of it. Recommended action on a finding: move the work to the Stage
5 backlog / handoff.

### Script runners

Interpreter selection: `<repo_root>/.venv/Scripts/python.exe` when present,
otherwise `sys.executable` (the deterministic stand-in for the documented
plain-`python` fallback — same intent, no PATH ambiguity). Scripts run with
`cwd=repo_root`, a 600-second timeout, and no network. Only the exit code and
the last non-empty stdout line (truncated to 160 chars) are recorded; the
security scanner already redacts its own findings, so no secrets are echoed.

`run_release_script` defaults to **False** because
`scripts/test_release.py` chains multiple sub-suites and is heavier than the
smoke tier. Run it manually before tagging or pushing a release:
`.venv\Scripts\python.exe scripts\test_release.py`.

A security-scan failure always produces a blocker: the baseline scanner
deliberately never scans docs, so a failure is a real finding in
executable/config scope, never a docs-only wording false positive.

### validate_static_forbidden_behavior

Scans `scos/commercial/*.py` executable source only (tests and docs are
excluded) for `import`/`from` lines that would introduce forbidden behavior:
network libraries, API-server frameworks, database drivers, money-capture
providers, relationship-management sync, messaging services, model-API
clients, or cloud-storage SDKs. Docs mentioning these capabilities as
non-goals never fail the check. Any finding is a **critical** blocker.

## Readiness scoring

Max score 100, split into buckets:

| Bucket | Weight | Checks covered |
|---|---|---|
| contract/source existence | 25 | validate_stage4_contract_files, validate_commercial_source_files |
| hardening foundation | 20 | validate_hardening_foundation |
| smoke/security scripts | 20 | run_smoke_script, run_security_scan_baseline |
| forbidden behavior scan | 15 | validate_static_forbidden_behavior |
| git/release safety | 10 | validate_git_state |
| Stage 5 handoff completeness | 10 | validate_stage5_handoff_readiness |

Bucket rule (deterministic): full weight when every covered check succeeded;
zero when any covered check failed; half weight (floor) when a covered check
was skipped without any failure. The optional release script is outside the
scored buckets.

## GO / NO-GO rules

- **GO** — score >= 90, no critical blockers, and no warnings
  (no failures, no blockers, no non-info skips). `readiness_level =
  stage4_complete`, `stage_closed = true`.
- **CONDITIONAL_GO** — score >= 75 and no critical blockers, with warnings
  present (or score below the GO threshold). `readiness_level =
  stage4_complete_with_warnings`, `stage_closed = true` only if
  `allow_warnings=True`.
- **NO_GO** — score < 75 or any critical blocker. `readiness_level =
  stage4_blocked`, `stage_closed = false`.

`accepted` mirrors `stage_closed`.

## Output JSON schema

When `output_path` is provided, the gate writes
`stage4_final_release_gate.json` (if `output_path` has a `.json` suffix it is
used verbatim; otherwise it is treated as a directory and the canonical
filename is appended). Top-level keys: `ok`, `schema_version`, `accepted`,
`release_gate_id`, `checked_at`, `stage`, `stage_closed`, `go_no_go`,
`readiness_level`, `readiness_score`, `readiness_max_score`, `checks`,
`blockers`, `stage5_handoff_items`, `output_path`, `metadata`.

## Deterministic serialization

Written via `manifest_tools.write_stable_json` (Stage 4.18):
`json.dumps(payload, sort_keys=True, indent=2)`, UTF-8, LF line endings,
trailing newline. Same inputs produce byte-identical output. The gate never
writes on the error path, never deletes files, never modifies inspected
files, and creates no directories except the output parent when needed.

## Local-only boundary

No network, no cloud, no LLM calls, no environment reads, no real clock, no
randomness, no uuid. `checked_at` is always caller-supplied.

## No Stage 4.20+ rule / no feature expansion rule

Stage 4 ends at Stage 4.19. The gate itself enforces that no Stage 4.20 or
later markers exist in certification/specification docs, and Stage 4.19 adds
no new commercial feature flow — it is a certification and handoff layer
only. Future work belongs in the Stage 5 backlog (`docs/roadmap/STAGE5_HANDOFF.md`).

## Stage 5 handoff rules

The gate emits ten deterministic `Stage5HandoffItem`s (ids `stage5-001` …
`stage5-010`) covering: Control Center backend, command API, event stream,
operator approval workflow, release provenance, SBOM / dependency
vulnerability tooling, artifact signing, first-customer workflow
productization, monitoring/maintenance hooks, and the real-integration
boundary + Stage 5 success criteria. `docs/roadmap/STAGE5_HANDOFF.md` must
exist; the items are design/handoff descriptions only — Stage 4.19 implements
none of them.

## Security / test strategy usage

The gate leans on the Stage 4.18 assets instead of re-implementing them:
`scripts/test_smoke.py` (Tier 1 sanity), `scripts/security_scan_baseline.py`
(static security baseline), `scripts/test_release.py` (heavier release tier,
manual/optional), `docs/testing/TEST_SUITE_STRATEGY.md` and
`docs/security/SECURITY_HARDENING_BASELINE.md` (verified to exist).

## Examples

```python
from pathlib import Path
from scos.commercial import run_stage4_final_release_gate

result = run_stage4_final_release_gate(
    repo_root=Path("."),
    checked_at="2026-07-05T00:00:00Z",
    output_path=Path("artifacts/stage4_final_release_gate.json"),
)
if result.ok and result.go_no_go == "GO":
    print("Stage 4 closed:", result.release_gate_id)
```

Waived-git local run (e.g. while Stage 4.19 files are still uncommitted):

```python
result = run_stage4_final_release_gate(
    repo_root=Path("."), checked_at="2026-07-05T00:00:00Z",
    require_clean_git=False,
)
```

## Failure modes

| error_kind / blocker | Meaning |
|---|---|
| `INVALID_ARGUMENTS` | missing/empty repo_root or checked_at, URL path |
| `INPUT_NOT_FOUND` | repo_root does not exist or is not a directory |
| `GIT_UNAVAILABLE` | git binary missing while `require_clean_git=True` |
| `GIT_STATE_FAILED` (blocker) | wrong branch, HEAD != origin/main, dirty tree |
| `CONTRACT_DOC_MISSING` (blocker) | required Stage 4 contract doc absent |
| `SOURCE_FILE_MISSING` (blocker) | required commercial source file absent |
| `HARDENING_ASSET_MISSING` (blocker) | Stage 4.18 asset absent |
| `STAGE_OVER_FRAGMENTATION` (blocker) | a forbidden Stage 4.20+ marker was found |
| `SMOKE_SCRIPT_FAILED` / `SECURITY_SCAN_FAILED` / `RELEASE_SCRIPT_FAILED` (blockers) | script exited nonzero |
| `FORBIDDEN_BEHAVIOR_DETECTED` (blocker) | forbidden import in executable source |
| `HANDOFF_DOC_MISSING` (blocker) | Stage 5 handoff doc absent |
| `OUTPUT_WRITE_FAILED` | gate report could not be written |
