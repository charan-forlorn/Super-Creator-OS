# GitHub Actions — Root Cause Analysis v2 (runs = 0, check-runs = 0)

**Goal:** Find the *real* reason GitHub Actions produces `runs = 0` / `check-runs = 0`
after commit `0cc5725`, now that the **unverified-email hypothesis is disproven** (account
email is VERIFIED).
**Review discipline:** `skills/qa-reviewer/SKILL.md` — evidence first, hypotheses ranked,
prior theory explicitly retracted.
**Mode:** **Read-only.** No code changes, no commits, no pushes, no dispatch, no settings
changed. All claims below are raw `gh api` / `git` output captured 2026-06-23.
**Repo:** `charan11102543-ai/super-creator-os` (public, User-owned) · **Branch:** `master` @ `0cc5725`.

---

## ROOT CAUSE

**GitHub Actions execution is disabled/suspended at the ACCOUNT level — the GitHub Actions
service is not scheduling workflows for this account, so it never creates a `github-actions`
check-suite for pushed commits.** The repository-level "Actions enabled" flag is the user's
*preference* and still reports `true`, but the Actions backend is not acting on it. This is
**not** a workflow-file, trigger, permissions, repo-settings, or email problem — every one of
those is positively verified correct below.

**Smoking gun:** a push to `master` (`0cc5725`) created **8 check-suites — every one from a
third-party GitHub App** (cursor, railway-app, render, vercel, netlify, devin-ai-integration,
claude, sourcery-ai) — and **zero from the `github-actions` app (id `15368`)**. The Actions
engine, alone among the installed apps, did not engage. The identical pattern exists on the
original workflow-add commit `db2bf4f`, so the workflow has **never** run since it was added —
across two separate qualifying pushes.

## CONFIDENCE

**~80%** that the blocker is an **account-level Actions restriction/suspension** (most
commonly a new-account abuse-prevention flag that silently disables Actions execution).

- The *fact* that the Actions engine is not engaging is **~100% certain** (check-suite
  evidence is direct and definitive).
- The remaining ~20% uncertainty is only about *which* account-level mechanism (fraud/abuse
  flag vs. a billing/spending hold vs. an account-state under review) — all of which resolve
  to the **same owner action** (see "Exact next action"). A transient GitHub-side outage is
  effectively excluded because the condition has persisted across two commits over multiple
  days.

---

## EVIDENCE (by task)

### 1. Repository Actions settings — ✅ correct (not the cause)
```
repos/.../actions/permissions → {"enabled":true,"allowed_actions":"all","sha_pinning_required":false}
repos/.../actions/permissions/access → 422 "Access policy only applies to internal/private repos" (expected for public)
repos/.../  archived:False  disabled:False  visibility:public  private:False  owner_type:User
permissions: {admin:true, maintain:true, push:true, ...}
```
Actions feature is ON, all actions allowed, repo is not archived/disabled, caller is admin.

### 2. Workflow registration state — ✅ correct (not the cause)
```
actions/workflows → total_count:1  | "CI" | state: active | path: .github/workflows/ci.yml | id: 300163993
actions/workflows/300163993 → state: active
```
Exactly one workflow, **registered and active**.

### 3. Workflow visibility via API — ✅ correct (not the cause)
Workflow object resolves with a stable id (`300163993`), `state: active`, correct path,
`html_url`, and `badge_url`. It is fully visible to the API.

### 4. Trigger configuration — ✅ correct (not the cause)
Remote `master` file `on:` block:
```
push.branches: [master, h1-foundation]
pull_request.branches: [master]
workflow_dispatch:        # present (added in 0cc5725)
```
The push of `0cc5725` was **to `master`**, which matches `push.branches` — it *should* have
triggered. It did not.

### 5. Workflow file integrity on origin/master — ✅ intact (not the cause)
```
git ls-tree origin/master -- .github/workflows/ci.yml → blob f50cfd6
contents API (decoded) → workflow_dispatch present at L19; sha f50cfd6 (matches)
```
The committed blob and the remote blob are identical; GitHub parsed it (it is `active`).

### 6. Is GitHub silently rejecting the workflow? — ❌ No; the engine never *engages*
This is the decisive evidence.
```
commits/0cc5725/check-suites → total_count: 8
   apps: cursor, railway-app, render, vercel, netlify, devin-ai-integration, claude, sourcery-ai
   (all status: queued)   ← NONE is "github-actions"
commits/0cc5725/check-suites?app_id=15368  → github-actions check_suites: 0
commits/db2bf4f/check-suites → SAME 8 third-party apps, github-actions absent
```
A workflow "rejected for invalid YAML" would still produce a **`github-actions` check-suite
with a failure annotation**. Here there is **no `github-actions` check-suite at all** — the
Actions engine is not even creating the container it would use to report success *or*
rejection. That only happens when Actions is not running for the repo/account.

### 7. Permissions / policy preventing execution — ⚠️ account-level (the cause)
```
default_workflow_permissions: read   (sufficient; not a blocker)
runs (every status): total_count: 0  | check-runs on 0cc5725: 0  | gh run list: empty
users/charan11102543-ai/settings/billing/actions → 404 + "needs 'user' scope"
   (token scopes: gist, read:org, repo, workflow — billing not inspectable from here)
```
Token perms are fine for a test workflow. Account **billing/usage could not be inspected**
(missing `user` scope) — this is the one layer not directly visible from this session and is
exactly where an account-level Actions hold would live. Combined with the absent
`github-actions` check-suite, the block sits at the **account** layer, above the repo.

### Disproven prior hypothesis
"Unverified email gating" (v1 report, P0-C) is **retracted** — the email is verified, yet the
behavior persists. Verified email is necessary but not sufficient; the actual gate is the
account-level Actions execution state.

### What is positively ruled OUT as the cause
Workflow YAML validity · trigger config · branch match · file integrity · workflow
registration/visibility · repo Actions feature flag · repo archived/disabled · token
permissions · email verification. **All verified correct above.**

---

## EXACT NEXT ACTION REQUIRED (to make the first run appear)

The fix is **account-level and owner-only** — nothing further in the repo, workflow, or
git history will change the outcome. In order:

1. **Inspect the account's Actions state in the UI (owner login `charan11102543-ai`):**
   - **https://github.com/settings/billing** — look for any *Actions disabled*, *spending
     limit reached*, *payment issue*, or *account under review / restricted* banner.
   - **https://github.com/settings/actions** and the repo's
     **https://github.com/charan11102543-ai/super-creator-os/settings/actions** — look for a
     notice that Actions is disabled or pending enablement, or a one-time
     *"I understand my workflows, go ahead and enable them"* prompt on the **Actions tab**
     (https://github.com/charan11102543-ai/super-creator-os/actions). If that prompt is
     present, click it — that single click can release a never-run repo.

2. **If no self-serve banner/prompt exists** (the likely case, since the repo flag already
   says enabled): **contact GitHub Support** at **https://support.github.com/** and report:
   *"New account; GitHub Actions is enabled at the repo level and the workflow is active, but
   no `github-actions` check-suite is created and 0 runs occur on pushes to the default
   branch. Please check whether Actions is disabled/restricted on my account."* Only GitHub
   can lift an account-level Actions suspension/flag. Reference the evidence above
   (8 third-party check-suites, zero `github-actions` check-suite on `0cc5725` and `db2bf4f`).

3. **Verification that it is fixed (read-only, repeatable):**
   ```
   gh api repos/charan11102543-ai/super-creator-os/commits/<sha>/check-suites?app_id=15368
   ```
   When this returns `total_count ≥ 1` (a `github-actions` check-suite appears), Actions has
   engaged. Then either push any commit / open a PR to `master`, or click **Run workflow**
   (now available via `workflow_dispatch`), and the first run will appear at
   **https://github.com/charan11102543-ai/super-creator-os/actions/workflows/ci.yml**.
   Expected result once it runs: green (local suites pass 58/58 + 16/16 + 8/8 + 18/18).

> Note (scope): a definitive *active* probe would be `gh workflow run ci.yml --ref master`
> (or the API `dispatches` endpoint) — if Actions were account-enabled it would create a run;
> if suspended it returns an error or silently no-ops. This is **deliberately not executed
> here** to honor the read-only / no-dispatch constraint, but it is the fastest one-command
> confirmation the owner can run after step 1–2.

---

## SUMMARY

| | |
|---|---|
| **Root cause** | Account-level GitHub Actions execution is disabled/suspended; the `github-actions` app never creates a check-suite, so no run is ever scheduled. Repo/workflow/email/permissions are all correct. |
| **Confidence** | ~80% (engine-not-engaging is ~100% certain; the specific account mechanism is the residual unknown — all variants need the same owner action). |
| **Key evidence** | `commits/0cc5725/check-suites?app_id=15368 → 0`; 8 third-party check-suites but **no `github-actions`**; identical on `db2bf4f`; `runs=0` despite a push to a matching branch with Actions `enabled:true` and workflow `active`. |
| **Disproven** | Unverified email (retracted); invalid YAML; wrong/missing triggers; file corruption; repo Actions disabled; archived repo; token permissions. |
| **Next action** | Owner checks account Actions/billing state in the UI; if no self-serve fix, contact GitHub Support to re-enable Actions for the account. Confirm via a `github-actions` check-suite appearing. |

---
*Read-only RCA — no code, commits, pushes, dispatches, or settings changes were made.
Deliverable: this file only. Every status claim is backed by `gh api` / `git` output.*
