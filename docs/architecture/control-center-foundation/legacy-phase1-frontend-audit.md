# Phase 1 Frontend Audit — Control Center Data Provenance Map

**Audit scope:** `apps/control-center` (Next.js 15 + React 19)
**Auditor:** Frontend Auditor (subagent)
**Date:** 2026-07-18 (updated 2026-07-19 for Phase 1.5)
**Mode:** READ-ONLY — no production code changed, no files deleted, no API routes modified.
**Goal (Phase 1 — Truthful Control Center):** map every route / card / counter / status / action to its data source, and flag where a "DEMO DATA" / "MOCK" badge is required so mock data is never presented as production state.

---

## 1. Headline findings

| Metric | Value |
|---|---|
| Total `*mock-data.ts` modules in `lib/` | **17** |
| `*mock-data.ts` modules consumed by an **active (reachable) route** | **0** |
| Hard-coded DEMO dataset (`DEMO_SNAPSHOT`) | **1** (in `lib/control-center-snapshot.ts`) — correctly gated behind an explicit DEMO mode toggle |
| Mock data touched only by **orphaned/dead code** | **16 modules** (via `components/app-shell.tsx`) |
| Orphaned top-level dashboard component | **`components/app-shell.tsx`** — imported by **zero** routes |
| Active UI surfaces (reachable) | Cockpit dashboard + 4 sub-routes + `hvs-render`, `solo-project-preparation`, `operator-dry-run` panels |
| Active UI surfaces currently reading mock data | **None** — all read real API routes or the gated DEMO set |

**Bottom line:** The currently-shipped Control Center (Cockpit) is already Phase-1 compliant. It reads LIVE data from a real read-only API route (`/api/control-center-snapshot`) and shows a prominent **"DEMO DATA — NOT LIVE SYSTEM STATE"** badge whenever the operator switches to demo mode. All mock-heavy code is confined to `AppShell` and its panels, which are **not wired into any route** — they are dead code, not live UI.

---

## 2. Active (reachable) UI — provenance map

| Route / Component | Data source | Live or Mock? | Badge status |
|---|---|---|---|
| `app/page.tsx` → `CockpitDashboard` | `useControlCenterData()` → GET `/api/control-center-snapshot` (or `DEMO_SNAPSHOT` when mode=DEMO) | **LIVE** (real file read of `data/control-center-snapshot.json`); DEMO is explicit opt-in | ✅ `SourceModeBadge` shows `DEMO_LABEL` in DEMO, "Live local read-only" in LIVE |
| `app/projects/page.tsx` → `ProjectsScreen` | `useControlCenterData()` (same bridge) | **LIVE** / opt-in DEMO | ✅ `SourceModeNote` badge |
| `app/approvals/page.tsx` → `ApprovalsScreen` | `useControlCenterData()` | **LIVE** / opt-in DEMO | ✅ badge + DEMO `LocalToast` |
| `app/evidence/page.tsx` → `EvidenceScreen` | `useControlCenterData()` | **LIVE** / opt-in DEMO | ✅ badge in action kicker |
| `components/hvs-render-panel.tsx` | `lib/hvs-render-client.ts` → GET `/api/hvs-render/projection` etc. (real API) | **LIVE** | ✅ no mock; real projection/authorize/execute/reconcile routes |
| `components/solo-project-preparation-panel.tsx` | `lib/project-preparation-client.ts` → `/api/project-preparation/*` (real API, writes `memory/runtime/control-center/project-preparation-v1.json`) | **LIVE** (authoritative store) | ✅ truth-from-backend, no mock |
| `components/operator-dry-run-panel.tsx` | `lib/operator-dry-run.ts` (validation) + GET/POST `/api/operator-dry-run` | **LIVE** | ✅ renders "Backend unavailable: showing deterministic unavailable dry-run response, not fake success" when backend missing — truthful, no fake success |

### Detail: the single DEMO dataset
- `lib/control-center-snapshot.ts` defines `DEMO_SNAPSHOT` and `DEMO_LABEL = "DEMO DATA — NOT LIVE SYSTEM STATE"`.
- `resolveCockpitView(mode, live)` guarantees: DEMO never falls back to LIVE, and LIVE failure never falls back to DEMO (instead returns `UNAVAILABLE` truthfully via `unavailableFallback()`).
- DEMO is **never auto-enabled** — it is only shown when the operator clicks "Switch to Demo". This satisfies the safety rule (no UI may claim live state from mock/fixture).

### Detail: the LIVE artifact is genuine
- `data/control-center-snapshot.json` has `"source_mode": "LIVE_LOCAL_READ_ONLY"` and the API route rejects any payload whose `source_mode` is not `LIVE_LOCAL_READ_ONLY`. So the LIVE view never shows fabricated numbers.
- **Phase 1.5 status-semantics correction (2026-07-19):** When the live read-surface read models (`approval_summary`, `event_summary`, `audit_summary`) contain records, the `Approvals` and `Evidence` dashboard sections now report `AVAILABLE_EMPTY` (zero records) or `AVAILABLE_WITH_DATA` (≥1 record) instead of the previously **incorrect** `UNAVAILABLE`. Only a genuinely missing read surface yields `UNAVAILABLE`. This is a value-semantics fix in `scos/control_center/control_center_snapshot.py`; the section schema (`available`/`status`/`data`/`reason_code`/`observed_at`) and status enum are unchanged, so no provenance-map binding rewrite is required. See `CHANGELOG.md` (Phase 1.5).

---

## 3. Orphaned / dead code — provenance map (NOT reachable from any route)

`components/app-shell.tsx` is imported by **nothing** (verified via grep across `app/` and `components/`). It is the sole importer of 16 mock-data modules and renders ~40 panels. None of it can be reached by a user.

| Component / Card | Source module | Should display as |
|---|---|---|
| `AppShell` (whole legacy dashboard) | `lib/mock-data.ts` + 15 stage mock modules | **DEAD** — remove or rewire. Currently unreachable; if ever re-exposed it MUST be DEMO-badged |
| Stage 5.1 Command Bridge (draft/approval/event log) | `lib/command-mock-data.ts` | Mock — already carries inline "mock data · no real execution" labels in sub-components |
| Stage 5.2 AI Work Sessions | `lib/ai-work-session-mock-data.ts` | Mock — sub-panels already labeled "mock data · no AI execution" |
| Stage 5.3 Agent Adapters | `lib/agent-adapter-mock-data.ts` | Mock — "real dispatch disabled" labels present |
| Stage 5.4 Prompt & Result Packets | `lib/prompt-result-packet-mock-data.ts` | Mock — "no real AI dispatch" labels present |
| Stage 5.5 Packet Review | `lib/operator-packet-review-mock-data.ts` | Mock — "Local mock decision selected" label |
| Stage 5.6 Workflow Router | `lib/workflow-router-mock-data.ts` (`sampleDecision`) | Mock — sidebar hint "Stage 5.6 mock" |
| Stage 5.7 Result Intake / ChatGPT loop | `lib/result-intake-mock-data.ts` | Mock |
| Stage 5.8 Git Commit/Push Approval | `lib/git-approval-mock-data.ts` | Mock — "inert mock" labels present |
| Stage 5.9 Operator Execution Console | `lib/operator-execution-mock-data.ts` | Mock |
| Stage 5.10 Certification | `lib/stage5-certification-mock-data.ts` | Mock |
| Stage 6.2 Local Backend / Command API | `lib/local-backend-mock-data.ts` | Mock — panels state "static, deterministic mock" |
| Stage 6.3 Durable State | `lib/durable-state-mock-data.ts` | Mock — "static, deterministic mock" labels |
| Stage 6.4 Event Stream / UI Sync | `lib/event-stream-mock-data.ts` | Mock |
| Stage 7.4 Operator Read Surface | `lib/operator-read-surface-mock-data.ts` | Mock fixture — "Static/Mock Fallback" label |
| Stage 7.6 Command Views | `lib/operator-command-view-mock-data.ts` | Mock fixture |
| Top/bottom: Agent status, Task board, Timeline, Merge queue, Result inbox, Next action, Handoff, Project snapshot, Evidence, Review archive, Live Work Updates, Mascot | `lib/mock-data.ts` (+ `lib/live-events.ts` derived from `TASKS`; `lib/review-gates.ts`) | Mock (deterministic). `Live Work Updates` is a replayed fixed event list — labeled implicitly via section heading; no explicit DEMO badge |
| `PromptBuilder` | `lib/mock-data.ts` (`AGENTS`) | Mock — reached only via AppShell |
| `WorkflowRouterPanel` | `lib/workflow-router-mock-data.ts` | Mock — reached only via AppShell; also has a direct `sampleDecision` import |

### Other orphan mock modules (referenced only by dead code / tests)
- `lib/cockpit-mock-data.ts` — **0 references** anywhere (fully dead).
- `lib/mock-data.ts` — 5 consumers: `app-shell.tsx`, `prompt-builder.tsx`, `lib/live-events.ts`, `lib/review-gates.ts`, `lib/utils.ts`. Of these, only `app-shell.tsx` is itself orphaned; `lib/live-events.ts`/`review-gates.ts`/`utils.ts` are utilities only used by `app-shell.tsx` (so the whole chain is dead).

---

## 4. Points that REQUIRE a "DEMO DATA" / "MOCK" badge (or hiding in LIVE mode)

### 4A. Reachable UI — already compliant (verify, do not change)
1. **Cockpit dashboard / projects / approvals / evidence** — DEMO badge present via `useControlCenterData` + `DEMO_LABEL`. ✅
2. **`hvs-render-panel`, `solo-project-preparation-panel`, `operator-dry-run-panel`** — these read REAL APIs, so the rule "no LIVE claim from mock" is satisfied by construction. They need **no** mock badge. ⚠️ Note: if the real backend is absent, they currently show "unavailable"/"deterministic unavailable response" — truthful, keep as-is.

### 4B. Dead code — would need badge ONLY if re-exposed (Phase 2+)
Every `AppShell` panel above must carry an explicit "DEMO DATA" badge before any of it is rewired into a route. Good news: **most sub-components already have inline "mock data · …" micro-labels** (e.g. `adapter-simulation-panel.tsx:40`, `command-draft-panel.tsx:69`, `operator-approval-panel.tsx:19`). Missing a top-level section banner are the *section wrappers* themselves — the mock label is only on inner cards, not on the `SectionHeading`. Recommended: if reactivated, add a `DEMO_LABEL` banner per section like the cockpit does.

### 4C. Explicit gaps even within dead code (no badge at all)
- `Live Work Updates` section — replayed fixed event list, no DEMO badge anywhere (only the section title).
- `Stage Overview` / `Handoff Status Strip` / `Project State Snapshot` / `Evidence Cards` / `Review Archive` / `Task Board` / `Timeline` / `Result Inbox` / `Merge Queue` / `Mascot` — all sourced from `lib/mock-data.ts`; only `sidebar.tsx` hints "mock" globally. No per-card DEMO banner.

---

## 5. Mock-points summary by category (count)

| Category | Count | Notes |
|---|---|---|
| Reachable LIVE-but-DEMO-gated surfaces | **4** | cockpit dashboard + 3 sub-routes; DEMO badge present |
| Reachable REAL-API panels (not mock) | **3** | hvs-render, solo-project-preparation, operator-dry-run |
| Orphaned mock-data modules (dead) | **16** | consumed only by `AppShell` |
| Fully-dead mock modules (0 refs) | **1** | `cockpit-mock-data.ts` |
| Inline "mock data" micro-labels already present | **~15** | across AppShell sub-components |
| Orphaned top-level dashboard | **1** | `app-shell.tsx` |

**Total distinct mock-surface points identified: ~20 (16 modules + inline-labeled cards + 1 DEMO-gated live surface set + 1 fully-dead module).**

---

## 6. Recommendations (for Phase 1 / Phase 2, non-blocking)

1. **No action required for the live UI** — it already satisfies the safety rule. Keep `DEMO_SNAPSHOT` opt-in only.
2. **Decide fate of `app-shell.tsx` + its 16 mock modules.** Either:
   - (a) delete the orphan (preferred if unplanned), or
   - (b) if it is the intended "full prototype" view, rewire it as a clearly-badged DEMO-only route (e.g. `/prototype` defaulting to DEMO mode with a global `DEMO_LABEL` banner), never LIVE.
3. **If reactivated, add a per-section `DEMO_LABEL` banner** to every `AppShell` section (currently only inner cards are labeled).
4. **Remove `lib/cockpit-mock-data.ts`** — zero references; pure dead weight.
5. **Keep the truthful unavailable behavior** in `operator-dry-run-panel` and the snapshot route — do not "improve" it into fake-success.

---

## 7. Verification performed
- `grep` for `mock-data` imports across `components/` + `app/` (only `app-shell.tsx`, `prompt-builder.tsx`, `workflow-router-panel.tsx`, and tests import them — all AppShell-only).
- `grep` confirming **zero** `mock-data` imports inside `components/cockpit/` and `app/` route screens.
- Confirmed `app-shell.tsx` is imported by **no** file (orphan).
- Read `lib/control-center-snapshot.ts`, `app/api/control-center-snapshot/route.ts`, and `data/control-center-snapshot.json` — DEMO/LIVE separation and truthful UNAVAILABLE handling verified.
- Read `hvs-render-client.ts`, `project-preparation-client.ts`, `operator-dry-run.ts` — confirmed real API fetch targets, no mock fallback.

**No code was modified. No files deleted. No API routes changed.**
