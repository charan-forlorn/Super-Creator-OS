# GitHub Actions / CI Audit — P0-5 ("CI not running")

**Goal:** Close P0-5 from `production_readiness_audit.md` — *"CI exists but does not run."*
**Mode:** **Read-only.** No code modified, no PR opened, no repository settings changed.
All findings are live evidence from `gh api` + `git` against the actual repo.
**Date:** 2026-06-23 · **Repo:** `charan11102543-ai/super-creator-os` (public, not a fork)
· **Default branch:** `master` @ `db2bf4f`.

> **Skill note (faithful reporting):** the task asked to "use the DevOps skill from this
> repository." **There is no DevOps skill in this repo** — `skills/` contains only
> storytelling, video-editor, retention-expert, qa-reviewer, social-media-manager,
> orchestrator (and a read/search/edit workspace agent that is explicitly barred from
> running shell commands). This audit was performed with DevOps discipline directly; no
> such skill was invoked because none exists.

---

## 1. Current status

| Check | Evidence (`gh api` / `git`) | Result |
|---|---|---|
| Actions feature enabled on repo | `repos/.../actions/permissions` → `{"enabled":true,"allowed_actions":"all"}` | ✅ **ENABLED** |
| Workflow registered | `repos/.../actions/workflows` → `total_count: 1`, *CI*, **state: active**, id `300163993` | ✅ active |
| Workflow file on default branch | `git ls-tree origin/master -- .github/workflows/` → `ci.yml` blob `2da357f` | ✅ present on `master` |
| Workflow file tracked & pushed | `git ls-files` ✓ tracked; `HEAD == origin/master == db2bf4f` (0 ahead / 0 behind) | ✅ pushed |
| YAML valid | GitHub registered it as **active** (server-side parse succeeded); structure well-formed | ✅ valid |
| **Runs ever executed** | `repos/.../actions/runs` → **`total_count: 0`**; workflow-scoped runs → `0`; `commits/master/check-runs` → `0` | ❌ **ZERO** |
| Secrets required by workflow | none referenced in `ci.yml` (no `${{ secrets.* }}`) | ✅ none needed |
| Default token permissions | `actions/permissions/workflow` → `default_workflow_permissions: read` | ✅ sufficient (test-only) |
| Branch protection / required checks | `branches/master/protection` → 404 *Branch not protected* | ⚠️ none (see P1-1) |
| Other workflow files | `contents/.github/workflows` → only `ci.yml` | ℹ️ single workflow |

**Headline:** the CI is **fully provisioned but has never run a single time.** The prior
audit's hypothesis — *"Actions appears disabled on the repo"* — is **incorrect and should
be corrected: Actions are ENABLED.** The blocker is upstream of settings.

---

## 2. Root cause

**No triggering event has ever been delivered to a runnable state, and the workflow has no
manual trigger to bootstrap one.**

Walking the evidence:

1. The workflow's `on:` block has **only `push` (branches `master`, `h1-foundation`) and
   `pull_request` (branches `master`)** — **no `workflow_dispatch`**, so there is *no way
   to start a run by hand*.
2. The commit that *added* the workflow (`db2bf4f`, "ci: add GitHub Actions workflow") is
   the current `origin/master` HEAD. Its check-runs count is **0** — i.e. pushing it did
   **not** produce a run.
3. Since that commit, **no new push and no pull request** has occurred (HEAD == origin,
   no open PRs), so the only two configured triggers have **never fired on a commit
   GitHub acted on**.
4. With Actions now enabled but the add-commit already in the past (GitHub does **not**
   retroactively run workflows) and **no `workflow_dispatch` escape hatch**, the repo is
   **wedged in a cold-start state**: nothing has triggered it, and nothing *can* be
   triggered manually.

**Why didn't pushing `db2bf4f` trigger a run?** Two non-exclusive candidates; remediation
is identical either way:

- **(Most likely) New-account Actions gating / email verification.** `charan11102543-ai`
  is a secondary/automation account (created 2025-12-22, `plan: None`). GitHub **silently
  refuses to run Actions for accounts whose primary email is unverified.** This produces
  exactly this fingerprint: Actions "enabled", workflow "active", **0 runs**, 0 check-runs.
  *Could not be confirmed via API* — the session token lacks the `user:email` scope
  (`gh api user/emails` is unauthorized), so **the user must confirm this in the UI**
  (Settings → Emails). This is the leading suspect.
- **(Or) Enablement-timing.** If Actions was toggled on *after* `db2bf4f` was pushed, the
  add-commit push saw Actions off → no run, and nothing has pushed since.

Either way, the **actionable root cause is structural**: *no fired trigger + no manual
trigger.* That is fully within the user's control to resolve.

---

## 3. Findings (P0 / P1 / P2)

### P0 — blocks "CI actually runs"
- **P0-A — Zero runs; workflow is dormant.** `total_count: 0`. The quality gate is
  theoretical (confirms the original P0-5).
- **P0-B — No `workflow_dispatch` trigger.** There is no manual way to bootstrap the first
  run; combined with the absent fired-trigger, the workflow cannot be started without a
  new push/PR. (The production-readiness audit already recommended adding this.)
- **P0-C — (Candidate, user-confirm) Account email unverified.** If true, Actions will
  **never** run regardless of YAML/triggers. Must be ruled out first — it would make every
  other fix futile.

### P1 — CI runs, but is not yet a real gate / has a platform blind spot
- **P1-1 — No branch protection / required status check on `master`.** `master` is
  unprotected, so even once CI is green, **nothing blocks a red push/merge.** A
  green-but-non-blocking workflow is not a gate.
- **P1-2 — CI runs on `ubuntu-latest` only; the project is Windows-primary.** The codebase
  is Windows-centric (UTF-8 shim, font assumptions) and the **just-landed P0-4 concurrency
  hotfix contains platform-branched Windows code** (`msvcrt.locking` in `_filelock.py`, and
  an `atomic_replace` retry that exists *specifically* for a Windows `os.replace`
  `ERROR_ACCESS_DENIED` flake). **None of that Windows path is exercised by an ubuntu
  runner** — the new `test_concurrency.py` would only validate the POSIX `fcntl` branch in
  CI. A `windows-latest` matrix leg is needed to actually guard the code we just shipped.

### P2 — hardening / coverage caveats
- **P2-1 — Render smoke self-skips in CI.** `integrations/shortgen/tests/test_smoke_pipeline.py`
  exits 0 when no clip is present (media is `.gitignored`), so the **real render path is
  unproven in CI** (documented in `ci.yml` header). Acceptable short-term; ship a tiny
  fixture clip later for a true render gate.
- **P2-2 — No dependency/vuln scan in CI** (`pip-audit`, Dependabot) and engine deps remain
  unpinned (R-3). Out of P0-5 scope but the natural next CI addition.
- **P2-3 — No coverage measurement / no `concurrency`-suite explicit step.** The new
  concurrency suite *is* covered transitively (it's wired as step `[9]` of
  `run_suite.py`), so the `ci.yml` "Learning layer suite" step does run it — but there is
  no coverage threshold or explicit naming.
- **OK (not findings):** YAML is valid; no secrets are required; `default_workflow_permissions:
  read` is correct for a test-only pipeline; all six test files the workflow invokes exist
  on disk; `concurrency.cancel-in-progress` is sensibly configured.

---

## 4. Exact remediation steps (read-only here — for the user to execute)

> Listed in dependency order. Steps 1–3 close P0-5; 4 closes the gate gap; 5 closes the
> Windows blind spot. None were performed by this audit.

1. **Rule out the silent killer first — verify the account email.**
   GitHub → **Settings → Emails** (https://github.com/settings/emails). Ensure the primary
   email shows **Verified**. If not, verify it — otherwise Actions will never run and every
   step below is wasted. *(Addresses P0-C.)*

2. **Add a manual trigger** so the workflow can be bootstrapped and re-run on demand.
   In `.github/workflows/ci.yml`, extend the `on:` block:
   ```yaml
   on:
     push:
       branches: [master, h1-foundation]
     pull_request:
       branches: [master]
     workflow_dispatch:        # <-- add: enables the "Run workflow" button
   ```
   *(Addresses P0-B. This is a one-line code change — left to the user since this audit is
   read-only and does not open a PR.)*

3. **Fire the first run.** After steps 1–2 land on `master`, either:
   - Actions tab → **CI → "Run workflow"** (now available via `workflow_dispatch`), **or**
   - push any trivial commit / open a PR to `master` to fire the existing `push`/`pull_request`
     triggers.
   Confirm green at https://github.com/charan11102543-ai/super-creator-os/actions.
   *(Addresses P0-A.)*

4. **Make it a real gate.** Once a green run exists: **Settings → Branches → Add branch
   ruleset/protection for `master`** → *Require status checks to pass* → select the **`test`**
   check (the job id in `ci.yml`). This blocks red merges. *(Addresses P1-1.)*

5. **Add a Windows runner leg** so the platform-specific lock/replace code is actually
   tested:
   ```yaml
   jobs:
     test:
       strategy:
         fail-fast: false
         matrix:
           os: [ubuntu-latest, windows-latest]
       runs-on: ${{ matrix.os }}
       # note: the ffmpeg apt-get step is Linux-only — guard it
       # (e.g. `if: runner.os == 'Linux'`) and install ffmpeg via choco/winget on Windows.
   ```
   *(Addresses P1-2 — directly validates the `msvcrt` branch + `atomic_replace` retry from
   the P0-4 hotfix.)*

---

## 5. Expected CI behavior (once remediated)

- **On every push to `master`/`h1-foundation` and every PR to `master`** (and on-demand via
  `workflow_dispatch`): GitHub spins an `ubuntu-latest` runner (and `windows-latest` after
  step 5), installs Python 3.11 + ffmpeg + `requirements.txt`, then runs:
  - **Learning-layer suite** (`run_suite.py`) — includes DQ, e2e closed-loop, **and the new
    concurrency regression as step `[9]`** → expected **58/58**.
  - **Highlight** engine + narrative tests.
  - **Short-gen** montage + generator + render-smoke (smoke **skips** cleanly with no media).
- **Concurrency** auto-cancels superseded runs on the same ref (`cancel-in-progress: true`).
- **Result contract:** any failing test → job exits non-zero → run is **red**. After step 4,
  a red `test` check **blocks merge to `master`**. The dormant-but-green illusion is gone:
  the suite that already passes locally (58/58 + 16/16 concurrency + 8/8 + 18/18) becomes an
  enforced, per-change gate.

---

## 6. Recommended fix order

1. **P0-C** — verify account email (UI). *Gates everything; 1 minute; do first.*
2. **P0-B** — add `workflow_dispatch` to `ci.yml`. *One line; unlocks manual bootstrap.*
3. **P0-A** — trigger the first run (dispatch or trivial push/PR); confirm green. *Closes P0-5.*
4. **P1-1** — branch-protect `master`, require the `test` check. *Turns CI into a gate.*
5. **P1-2** — add `windows-latest` to the matrix. *Covers the Windows lock/replace code.*
6. **P2-2 / P2-1 / P2-3** — `pip-audit` + Dependabot; ship a tiny render fixture; add coverage. *Hardening.*

**Bottom line:** P0-5's real cause is **not** disabled Actions (they're on) — it's a
**cold-start with no fired trigger and no manual `workflow_dispatch`**, most likely sitting
behind an **unverified-account Actions gate**. Verify the email, add the one-line manual
trigger, fire one run, then protect the branch — and the already-passing test suite becomes
a live, enforced CI gate. Adding a Windows runner is the one extra step that makes CI
actually cover the platform this project (and its newest hotfix) targets.

---
*Read-only audit — no code, PRs, or repository settings were changed. Deliverable: this
file only. All status claims are backed by `gh api` / `git` output captured 2026-06-23.*
