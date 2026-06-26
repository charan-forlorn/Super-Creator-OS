# GitHub Actions Fix Report — P0-B (`workflow_dispatch`)

**Goal:** Smallest safe fix to close **P0-B** from `github_actions_audit.md` — the CI
workflow had no manual trigger, leaving the dormant (0-run) workflow with no way to be
bootstrapped from the UI.
**Review discipline:** qa-reviewer ("catch problems before export") — change validated and
diffed before sign-off.
**Date:** 2026-06-23 · **Repo:** `charan11102543-ai/super-creator-os` · **Default branch:** `master`.

> Note: the `qa-reviewer` skill is a repository checklist file (`skills/qa-reviewer/SKILL.md`),
> not a runtime-invocable Skill — its pre-export verification discipline was applied here
> (validate syntax, verify no existing triggers changed, confirm CI behavior preserved).

---

## 1. Files changed

| File | Change | Lines |
|---|---|---|
| `.github/workflows/ci.yml` | Added a `workflow_dispatch:` trigger to the existing `on:` block | **+1 / −0** |

**Only one file was modified by this task.** `git diff --stat` → `1 file changed, 1 insertion(+)`.

> Other files shown as modified in the working tree (`integrations/learning/anchor_library.py`,
> `telemetry.py`, `memory_writer.py`, `tests/run_suite.py`, `CLAUDE.md`) are **pre-existing
> uncommitted changes from the earlier P0-4 concurrency hotfix** — they were **not touched
> in this task** and are unrelated to this fix.

No test commands, no job/step definitions, no existing triggers, and no other files were changed.

---

## 2. Exact YAML diff

```diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 2da357f..f50cfd6 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -16,6 +16,7 @@ on:
     branches: [master, h1-foundation]
   pull_request:
     branches: [master]
+  workflow_dispatch:        # manual "Run workflow" button (bootstraps the first run)
 
 # Cancel an in-flight run when a newer commit is pushed to the same ref.
 concurrency:
   group: ci-${{ github.ref }}
   cancel-in-progress: true
```

Resulting `on:` block:
```yaml
on:
  push:
    branches: [master, h1-foundation]
  pull_request:
    branches: [master]
  workflow_dispatch:        # manual "Run workflow" button (bootstraps the first run)
```

`workflow_dispatch:` with no value is valid — it registers the manual trigger with default
behavior (runs against the chosen branch, no custom inputs).

---

## 3. Local validation run

Strongest validation available locally (no `actionlint`/`yamllint`/`pyyaml` installed; the
venv has no pip). Used an **ephemeral** PyYAML via `uv run --with pyyaml` — nothing was
installed into the project environment, no files added.

```
$ uv run --with pyyaml python  (parse .github/workflows/ci.yml)
YAML parsed OK.
on triggers: ['push', 'pull_request', 'workflow_dispatch']
push.branches: ['master', 'h1-foundation']        # unchanged
pull_request.branches: ['master']                 # unchanged
workflow_dispatch: None (None = valid, uses defaults)
jobs: ['test']                                    # unchanged
test runs-on: ubuntu-latest | steps: 7            # unchanged
ALL CHECKS PASS
```

qa-reviewer checklist:

| Task | Result |
|---|---|
| 1. Add `workflow_dispatch` to `ci.yml` | ✅ added (1 line) |
| 2. Validate workflow syntax | ✅ parses cleanly; all three triggers present |
| 3. No existing triggers changed | ✅ `push` + `pull_request` branch lists byte-identical |
| 4. Preserve current CI behavior | ✅ `jobs`, `runs-on`, 7 steps, `concurrency` untouched |
| 5. Test commands not modified | ✅ no step `run:` lines in the diff |
| Only related file changed | ✅ `git diff --stat` = 1 file, +1 |

*Note:* PyYAML is a syntax/shape check, not GitHub's exact parser. The authoritative
server-side validation happens when the branch is pushed (GitHub re-registers the workflow)
— see §6.

---

## 4. Expected GitHub UI changes

Once this commit is **pushed to `master`** (GitHub re-parses the workflow on push):

1. **Actions tab → CI workflow** gains a **"Run workflow"** button (top-right of the
   workflow's run list). It was absent before because a workflow only shows that button
   when it declares `workflow_dispatch`.
2. Clicking **Run workflow** opens a small dropdown to pick the **branch** (default
   `master`) and a green **Run workflow** confirm button. No input fields appear (none were
   defined — intentional, smallest change).
3. The workflow remains listed as **active**; the existing `push`/`pull_request` automation
   is unchanged and still appears as run causes when those events fire.

---

## 5. Expected first-run behavior

When the first run is started (via the button in §6, or any push/PR):

- GitHub queues one run on `ubuntu-latest`, attributed to event **`workflow_dispatch`**
  (or `push`/`pull_request`).
- Steps execute in order: Checkout → Set up Python 3.11 → Install ffmpeg → Install
  `requirements.txt` → **Learning-layer suite** (`run_suite.py`, includes DQ + e2e +
  concurrency step `[9]`) → **Highlight** tests → **Short-gen** tests (render smoke
  self-skips, no media in CI).
- **Expected result: green.** The same suites pass locally — `run_suite.py` 58/58
  (incl. concurrency 16/16), evaluator 8/8, telemetry_capture 18/18. The render-smoke step
  exits 0 by design when no clip is present.
- `concurrency.cancel-in-progress: true` still applies: a newer push to the same ref
  cancels an in-flight run (does not affect a manual dispatch you start deliberately).

This converts the workflow from **0 runs (dormant)** to **a run you can start on demand** —
closing P0-B and unblocking the P0-A "fire the first run" step from the audit.

---

## 6. How to manually trigger the first run from the GitHub UI

**Prerequisite (from the audit, P0-C):** confirm the account's primary email is **Verified**
at **Settings → Emails** (https://github.com/settings/emails). If unverified, Actions will
not run regardless of this fix — verify it first.

**Prerequisite:** this commit must be on `master` on GitHub. `workflow_dispatch` only takes
effect once the workflow file **containing it** exists on the branch you dispatch from
(GitHub reads the trigger list from the branch's copy of the file). So commit + push first:

```bash
# (the user runs these — this task did not commit or push)
git add .github/workflows/ci.yml
git commit -m "ci: add workflow_dispatch trigger (close P0-B)"
git push origin master
```

Then, in the browser:

1. Go to **https://github.com/charan11102543-ai/super-creator-os/actions**.
2. In the left sidebar, click the **CI** workflow.
3. On the right, click the **"Run workflow"** ▾ button.
4. In the dropdown, leave **Use workflow from: `master`** (default).
5. Click the green **Run workflow** button.
6. Refresh; a new run appears at the top of the list with a yellow ● (queued/in-progress).
   Click it to watch the **test** job stream its steps.
7. Expect it to finish **green** (✓). That green run is the first-ever CI execution.

**After it's green (recommended next, from the audit — not part of this fix):** protect
`master` and require the **`test`** status check (Settings → Branches) so CI becomes an
enforced merge gate (audit P1-1), and consider adding a `windows-latest` matrix leg to
cover the Windows-specific lock code (audit P1-2).

---

## 7. Summary

- **Smallest safe change:** one line (`workflow_dispatch:`) added to `on:` in `ci.yml`.
- **Nothing else touched:** existing triggers, jobs, steps, test commands, and all other
  files are byte-for-byte unchanged.
- **Validated locally:** YAML parses; all three triggers present; CI shape preserved.
- **Result:** the workflow gains a UI "Run workflow" button after push, enabling the first
  manual run — P0-B closed, P0-A (fire first run) unblocked.

---
*This task modified only `.github/workflows/ci.yml` (+1 line). It did not commit, push, open
a PR, or change repository settings. Deliverable: this report + the one-line workflow change.*
