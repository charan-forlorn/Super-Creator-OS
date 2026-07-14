# SCOS–HVS Production Operations Runbook

Operator guide for running the SCOS → Hermes Video Studio (HVS) production
lifecycle end-to-end. Read-only inspection commands never mutate state.

---

## 1. Canonical Startup Checks

```powershell
cd C:\Workspace\super-creator-os
git rev-parse --show-toplevel        # must be C:\Workspace\super-creator-os
git branch --show-current            # main
git status --short --untracked-files=all   # only operator artifacts untracked

cd C:\Workspace\hermes-video-studio
git rev-parse HEAD                   # 2d55b371656c45c18e24a997a69025abd21ac4e685e
git status --porcelain=v1 -uall      # must be empty (tracked tree clean)
```

- SCOS interpreter: `C:\Workspace\super-creator-os\.venv\Scripts\python.exe`
- HVS interpreter: `C:\Workspace\hermes-video-studio\.venv\Scripts\python.exe`

## 2. Inspect Lifecycle Status (read-only)

```powershell
cd C:\Workspace\super-creator-os
.venv\Scripts\python.exe -m scos.control_center.cli `
    inspect-hvs-lifecycle --project-id <PROJECT_ID>
.venv\Scripts\python.exe -m scos.control_center.cli `
    inspect-hvs-next-action --project-id <PROJECT_ID>
.venv\Scripts\python.exe -m scos.control_center.cli `
    verify-hvs-lifecycle --project-id <PROJECT_ID>
```

Output is structured JSON: `state` (UNKNOWN/READY/BLOCKED/COMPLETED),
`current_stage`, `blockers`, `next_action`, `identity_chain`, `boundary_flags`.

## 3. Determine the Next Action

The inspector's `next_action` field returns exactly one allowed operator
action (or `no_further_automatic_action` when terminal). If `state` is
`BLOCKED`, the `blockers` list names the exact missing evidence.

## 4. Project Initialization (8L) — via approved HVS CLI

```powershell
cd C:\Workspace\hermes-video-studio
.venv\Scripts\python.exe -m hvs.cli initialize-project `
    --project-id <PROJECT_ID> --contract-path <CONTRACT_JSON> `
    --expected-payload-hash <HASH> --approve-initialization
```

## 5. Asset Intake / Materialization (8M) — via approved HVS CLI

```powershell
.venv\Scripts\python.exe -m hvs.cli import-media `
    --project-id <PROJECT_ID> --source-path <FILE> --media-type <TYPE>
```

## 6. Render Approval (8N) — SCOS service

Use `evaluate_render_request_readiness` + `approve_render` (explicit operator
approval). Render approval is a **separate** boundary from materialization.

## 7. Real Render (8N) — via approved HVS CLI

```powershell
.venv\Scripts\python.exe -m hvs.cli render-hyperframes `
    --project-id <PROJECT_ID> --format vertical
```

Then verify with SCOS `verify_render_artifact` (FFprobe subprocess). The
no-overwrite policy refuses to replace an existing successful artifact.

## 8. Artifact Verification (8N)

`verify_render_artifact(...)` checks width/height/fps/codec/pixel-format/
duration against the approved contract and records SHA-256. Non-matching
artifacts fail closed.

## 9. Delivery Authorization (8O) — SCOS service

`create_approval_request` + `decide_approval` (explicit). Manual delivery is a
local evidence record only — **no external transport**.

## 10. Receipt / Customer Outcome (8P)

`record_customer_receipt_evidence` + `record_customer_decision`. SCOS never
infers acceptance; the operator records the evidence.

## 11. Route Approval (8Q)

`create_post_delivery_route` + `decide_post_delivery_route` (explicit
approval). Distinct from the 8R action approval.

## 12. Resolution Execution (8R)

`create_execution_request` → `approve_execution_request` (separate explicit
approval) → `execute_approved_action`. Exactly one target mutation is recorded
append-only; replay is idempotent; changed semantics conflict.

## 13. Revision Handling

Open a REVISION_ELIGIBILITY_REVIEW route → 8R revision request creation. The
original artifact hash is preserved; the successor version is deterministic.

## 14. Dispute Handling

Open a DISPUTE_ELIGIBILITY_REVIEW route → 8R dispute opening. Delivery is NOT
auto-closed; no refund; no payment mutation; no customer contact.

## 15. Follow-Up Handling

Open a MANUAL_FOLLOW_UP route → 8R follow-up record. No customer message sent;
no external task created.

## 16. Interrupted-Session Resume

All state is append-only per store on disk. Restart the process and re-run the
inspector; approvals and completed targets are re-read from disk. A stopped
process that had approved-but-not-executed resumes and re-runs pre-execution
reverification before executing exactly one mutation.

## 17. Tool-Call-Limit Resume Block

If a session is interrupted by a tool/context limit: stop at a verified
checkpoint, preserve the worktree (no commit), and record a Resume Block with
SCOS_HEAD, HVS_HEAD, current checkpoint, and the last successful command. A
future session reconciles actual repo state and continues — do NOT restart
Stage 8S from zero.

## 18. Test and Security Commands

```powershell
cd C:\Workspace\super-creator-os
.venv\Scripts\python.exe -m pytest -q                       # full suite (integration deselected)
.venv\Scripts\python.exe -m pytest -m integration -q       # real-HVS integration
.venv\Scripts\python.exe scripts/test_smoke.py             # smoke (16 passed)
.venv\Scripts\python.exe scripts/security_scan_baseline.py # security (504/0)
```

## 19. Runtime-Path Locations

- SCOS work dir: `scos/work/` (append-only ledgers, gitignored).
- HVS projects: `C:\Workspace\hermes-video-studio\projects/<PROJECT_ID>/`
  (renders/, assets/, gitignored).
- HVS runtime is never committed.

## 20. Safe Task-Owned Cleanup

Remove only temporary fixture files created by your own acceptance run
(`.pytest-tmp-*`, task-owned probe artifacts). **Never** delete previous user
projects or media. Verify no runtime path enters Git with
`git status --short --untracked-files=all`.

## 21. Git Commit Policy

Stage changes use explicit-path staging (no `git add .` / `git add -A`).
Only Stage 8S-owned files are committed. Operator files
(`memory/database.json`, `.hermes/*.pdf`, `scripts/*`) are excluded.

## 22. No-Push Policy

Never push, deploy, publish, or contact customers. Certification is local.

## 23. Common Blocker Classifications

- `project_not_found_in_any_authoritative_store` — wrong project id or not yet initialized.
- `8R_resolution_action_execution` in blockers — route approved but 8R action not yet executed.
- identity mismatch — 8O artifact ≠ 8P receipt; routing/execution blocked.
- render verification failure — FFprobe mismatch; downstream blocked.

---

*Generated for Stage 8S final production release certification.*
