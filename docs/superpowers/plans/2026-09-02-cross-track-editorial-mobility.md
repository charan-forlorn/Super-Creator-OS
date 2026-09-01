# Cross-Track Editorial Mobility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let video/audio clips move atomically between compatible tracks by pointer drag while preserving CommandBus authority, exact undo/redo, snapping, selection, Preview≈Export, save/reopen, and Phase 4 invariants.

**Architecture:** Extend `MOVE_CLIP` with optional `targetTrackId`, keep Project v2 canonical, and use the existing CommandBus batch transaction for group moves. Add one pure desktop move-planning helper for same-kind lane-delta mapping and DOM track-hit resolution; Timeline remains the gesture coordinator while Preview/Rust continue deriving only from persisted Project membership.

**Tech Stack:** TypeScript 5.6, React 18, Zustand 4, Zod, Vitest 2, Tauri 2, WebView2/tauri-driver, Rust/FFmpeg, pnpm 11.

**Spec:** `docs/superpowers/specs/2026-09-01-cross-track-editorial-mobility-design.md`

## Global Constraints

- Phase 4 rollback baseline is `001a4e9910b16dc256d09bbf70b3b733f228a861`.
- Project schema remains v2; do not introduce schema v3 or migration work.
- Persisted Project remains canonical truth; runtime drag/drop state is never persisted.
- Every production mutation must flow through CommandBus; UI validation is advisory only.
- Existing `{ clipId, newStart }` MOVE_CLIP callers must remain behaviorally unchanged.
- Source and destination track locks are fail-closed authority boundaries.
- Only video→video and audio→audio cross-track movement is valid; text tracks are not clip destinations in this slice.
- Mixed video+audio selections may move horizontally but vertical group movement is rejected atomically.
- Alt bypasses magnetic snapping only; it never bypasses lock/kind validation.
- Preview and Rust renderer must not gain a separate remapping layer.
- Exact-path staging only; never use `git add .`, `git reset --hard`, or `git clean`.
- Do not stage/reset/reformat unrelated Control Center/SCOS dirty work.

---## File Structure

- `packages/command-system/src/commands.ts` — canonical cross-track move validation/mutation/inverse.
- `packages/command-system/tests/phase5-cross-track-move.test.ts` — command authority and undo/redo acceptance.
- `packages/command-system/dist/commands.js` + `commands.d.ts` — tracked build output after command-system source changes.
- `apps/desktop/src/crossTrackMove.ts` — pure same-kind group lane mapping and rendered-track hit resolution; no Zustand/DOM globals.
- `apps/desktop/tests/cross-track-move.test.ts` — pure planner and hit-resolution tests.
- `apps/desktop/src/store.ts` — CommandBus dispatch, atomic group commit, selected-track currentization, error projection.
- `apps/desktop/tests/cross-track-store.test.ts` — store transaction/selection/error tests.
- `apps/desktop/src/components/Timeline.tsx` — pointer capture, destination resolution, preview classes, commit orchestration.
- `apps/desktop/src/styles.css` — valid/invalid destination drag affordances only.
- `apps/desktop/tests/cross-track-timeline.test.ts` — pure/renderable Timeline helper/UI state contract where SSR is reliable.
- `apps/desktop/e2e/run-p5-cross-track-editorial-mobility.mjs` — real WebDriver pointer acceptance.
- `apps/desktop/e2e/run-p5-cross-track-qualification.mjs` — save/reopen + Preview/Export destination semantics using production commands.
- `integrations/video-studio/CHECKPOINT.md` — terminal evidence only after fresh qualification.

### Task 1: Extend MOVE_CLIP Command Authority

**Files:**
- Create: `packages/command-system/tests/phase5-cross-track-move.test.ts`
- Modify: `packages/command-system/src/commands.ts:128-154`
- Rebuild: `packages/command-system/dist/commands.js`, `packages/command-system/dist/commands.d.ts`

**Interfaces:**
- Consumes: existing `findClip`, `findTrack`, `assertTrackUnlocked`, `recomputeDuration`.
- Produces: `moveClipSchema = { clipId, newStart, targetTrackId? }`; `MOVE_CLIP` restores both `trackId` and `start` on inverse.
- [ ] **Step 1: Write CommandBus RED tests**

Add fixtures with two video tracks, two audio tracks, one locked track, and exact assertions for containment + `clip.trackId`:

```ts
it("moves a video clip to an explicit compatible destination", () => {
  const source = track("v1"); source.clips = [clip("c", "v1", 1)];
  const bus = busWithTracks([source, track("v2")]);
  bus.execute("clip.move", { clipId: "c", newStart: 4, targetTrackId: "v2" });
  expect(bus.project.tracks.find(t => t.id === "v1")?.clips).toHaveLength(0);
  expect(bus.project.tracks.find(t => t.id === "v2")?.clips[0]).toMatchObject({ id: "c", trackId: "v2", start: 4 });
});

it("undoes and redoes membership plus time exactly", () => {
  // v1@1 -> v2@4 -> undo v1@1 -> redo v2@4
});
```

Also assert: audio→audio PASS; missing target throws `CLIP_MOVE_TARGET_TRACK_NOT_FOUND`; video→audio throws `CLIP_MOVE_TARGET_TRACK_KIND_MISMATCH`; source/destination locked throw `TRACK_LOCKED`; same-track caller without `targetTrackId` remains unchanged.

- [ ] **Step 2: Run focused RED**

Run: `pnpm --filter @haios/command-system test -- phase5-cross-track-move.test.ts`
Expected: FAIL because `moveClipSchema` strips/rejects `targetTrackId` and membership does not change.

- [ ] **Step 3: Implement minimal command authority**

Use the existing command rather than introducing another movement command:

```ts
export const moveClipSchema = z.object({
  clipId: z.string().min(1), newStart: z.number().nonnegative(), targetTrackId: z.string().min(1).optional(),
});
```
```ts
execute(prev, { clipId, newStart, targetTrackId }) {
  const { clip, track: source } = findClip(prev, clipId);
  assertTrackUnlocked(source);
  const destination = targetTrackId
    ? prev.tracks.find((track) => track.id === targetTrackId)
    : source;
  if (!destination) throw new CommandError(`CLIP_MOVE_TARGET_TRACK_NOT_FOUND: ${targetTrackId}`);
  if (destination.kind !== source.kind) throw new CommandError(`CLIP_MOVE_TARGET_TRACK_KIND_MISMATCH: ${destination.id}`);
  assertTrackUnlocked(destination);
  const moved = { ...clip, start: newStart, trackId: destination.id };
  // same-track: replace in place; cross-track: remove once from source, append once to destination.
  // inverse payload: { clipId, newStart: clip.start, targetTrackId: source.id }
}
```

Do not sort persisted destination arrays here; Phase 4 composition already applies canonical start→code-point ordering where render order requires it.

- [ ] **Step 4: Run focused GREEN + legacy command regression**

Run:
- `pnpm --filter @haios/command-system test -- phase5-cross-track-move.test.ts`
- `pnpm --filter @haios/command-system test -- phase4-multitrack-authority.test.ts`
Expected: all PASS, including existing locked `clip.move` coverage.

- [ ] **Step 5: Rebuild tracked command-system dist and smoke it**

Run: `pnpm --filter @haios/command-system build`
Then run a Node import against `packages/command-system/dist/index.js` that moves `c` from `v1` to `v2`, undoes, and redoes.
Expected: source/dist semantics match and dist contains optional `targetTrackId` typing.

- [ ] **Step 6: Commit Task 1 exact scope**

```bash
git add packages/command-system/src/commands.ts packages/command-system/tests/phase5-cross-track-move.test.ts packages/command-system/dist/commands.js packages/command-system/dist/commands.d.ts
git diff --cached --check
git commit -m "feat(video-studio): add cross-track move authority"
```
### Task 2: Add Pure Cross-Track Move Planner

**Files:**
- Create: `apps/desktop/src/crossTrackMove.ts`
- Create: `apps/desktop/tests/cross-track-move.test.ts`

**Interfaces:**
- Produces `TrackRect = { trackId: string; top: number; bottom: number }`.
- Produces `resolveTrackAtClientY(rects: TrackRect[], clientY: number): string | null`.
- Produces `CrossTrackMovePayload = { clipId: string; newStart: number; targetTrackId?: string }`.
- Produces `buildCrossTrackMovePlan(project, selectedClipIds, anchorClipId, deltaSec, anchorTargetTrackId?)` returning `{ moves, primaryDestinationTrackId, vertical }`.

- [ ] **Step 1: Write planner RED tests**

Cover rectangle hit resolution, horizontal mixed-kind movement, same-kind lane delta, multi-source relative spacing, out-of-range destination, mixed-kind vertical movement, and missing selected clips.

```ts
const plan = buildCrossTrackMovePlan(project, ["a", "b"], "a", 2, "v2");
expect(plan.moves).toEqual([
  { clipId: "a", newStart: 2, targetTrackId: "v2" },
  { clipId: "b", newStart: 7, targetTrackId: "v3" },
]);
expect(plan.primaryDestinationTrackId).toBe("v2");
```
- [ ] **Step 2: Run focused RED**

Run: `pnpm --filter @haios/desktop test -- cross-track-move.test.ts`
Expected: FAIL because the pure planner does not exist.

- [ ] **Step 3: Implement deterministic Project-order mapping**

Implementation rules:
1. resolve every selected clip from `project.tracks`; if any ID is missing, fail without producing a partial plan;
2. clamp the whole group's horizontal delta so its minimum start is exactly `0`, preserving current group-spacing behavior;
3. if no cross-track destination is requested, emit same-track payloads without `targetTrackId`;
4. for a vertical move, require every selected clip source kind to equal the anchor source kind;
5. compute compatible tracks from canonical `project.tracks` order;
6. derive one `laneDelta` from anchor source index to anchor destination index;
7. map every selected source index through that same delta; any out-of-range destination invalidates the whole plan;
8. preserve selected-ID order in returned payloads, never DOM iteration order.

Use stable desktop planner errors such as `CROSS_TRACK_SELECTION_KIND_MISMATCH`, `CROSS_TRACK_DESTINATION_OUT_OF_RANGE`, and `CROSS_TRACK_SELECTED_CLIP_NOT_FOUND` for pre-command diagnostics. CommandBus remains final authority for target existence/kind/lock.

- [ ] **Step 4: Run planner GREEN + desktop typecheck**

Run:
- `pnpm --filter @haios/desktop test -- cross-track-move.test.ts`
- `pnpm --filter @haios/desktop typecheck`
Expected: PASS.

- [ ] **Step 5: Commit Task 2 exact scope**

```bash
git add apps/desktop/src/crossTrackMove.ts apps/desktop/tests/cross-track-move.test.ts
git diff --cached --check
git commit -m "feat(video-studio): plan cross-track group moves"
```
### Task 3: Wire Store Transactions and Selection Continuity

**Files:**
- Modify: `apps/desktop/src/store.ts:144-149, 512-548`
- Create: `apps/desktop/tests/cross-track-store.test.ts`

**Interfaces:**
- `moveSelected(newStart: number, targetTrackId?: string): boolean`.
- `commitGroupMove(deltaSec: number, anchorClipId?: string, anchorTargetTrackId?: string): boolean`.
- Both methods update `selectedTrackId` only after successful CommandBus mutation.
- Group method consumes `buildCrossTrackMovePlan` from Task 2 and submits one `bus.batch()`.

- [ ] **Step 1: Write store RED tests**

Use `useStudio.setState`/existing store setup patterns to load Project v2 fixtures, select clips, and call store actions directly.

```ts
expect(store.moveSelected(3, "v2")).toBe(true);
expect(useStudio.getState().project.tracks.find(t => t.id === "v2")?.clips[0].trackId).toBe("v2");
expect(useStudio.getState().selectedTrackId).toBe("v2");
expect(useStudio.getState().canUndo()).toBe(true);
```

Also prove: failed destination keeps `selectedTrackId`; same-kind group maps by lane delta; mixed-kind vertical returns false with no Project change; one undo restores every membership/time; redo re-applies all; missing selected ID causes zero mutation.

- [ ] **Step 2: Run focused RED**

Run: `pnpm --filter @haios/desktop test -- cross-track-store.test.ts`
Expected: FAIL because store methods accept no destination and group movement is horizontal-only.

- [ ] **Step 3: Implement store wrappers without bypassing CommandBus**

For single move:

```ts
const result = get().bus.execute(MOVE_CLIP, { clipId: id, newStart, targetTrackId });
set({ project: get().bus.project, dirty: true, lastError: null,
  selectedTrackId: targetTrackId ?? currentClip.trackId });
return true;
```
For group move, call the pure planner, then submit exactly one batch:

```ts
const plan = buildCrossTrackMovePlan(get().project, ids, anchorClipId ?? get().selectedClipId!, deltaSec, anchorTargetTrackId);
get().bus.batch(plan.moves.map((payload) => ({ commandType: MOVE_CLIP, payload })));
set({ project: get().bus.project, dirty: true, lastError: null,
  selectedTrackId: plan.primaryDestinationTrackId });
return true;
```

If planning or CommandBus fails: set only `lastError`, return false, and leave Project/selection/selectedTrackId untouched.

Preserve the existing whole-group clamp behavior for horizontal movement by keeping it inside the pure planner, not duplicating it in store.

- [ ] **Step 4: Run store GREEN + existing movement regressions**

Run:
- `pnpm --filter @haios/desktop test -- cross-track-store.test.ts`
- `pnpm --filter @haios/desktop test -- marquee-selection.test.ts ripple-workflow.test.ts timeline-edit-workflow.test.ts`
- `pnpm --filter @haios/desktop typecheck`
Expected: PASS.

- [ ] **Step 5: Commit Task 3 exact scope**

```bash
git add apps/desktop/src/store.ts apps/desktop/tests/cross-track-store.test.ts
git diff --cached --check
git commit -m "feat(video-studio): commit atomic cross-track moves"
```

### Task 4: Integrate Vertical Pointer Gestures in Timeline

**Files:**
- Modify: `apps/desktop/src/components/Timeline.tsx`
- Modify: `apps/desktop/src/styles.css`
- Create: `apps/desktop/tests/cross-track-timeline.test.ts`

**Interfaces:**
- Consumes `resolveTrackAtClientY` from Task 2.
- Consumes store `moveSelected(newStart, targetTrackId?)` and `commitGroupMove(deltaSec, anchorClipId?, anchorTargetTrackId?)` from Task 3.
- Runtime-only drag state adds anchor ID, start Y, source track IDs, current target ID, and validity; nothing enters Project.
- [ ] **Step 1: Write Timeline RED tests around exported pure/render helpers**

Avoid source-string assertions. Export only small helpers/components that are safe to render in isolation, for example a `CrossTrackDropIndicator` receiving `{ targetTrackId, valid }` and test its stable data attributes/classes.

Assert:
- valid target renders `data-cross-track-drop="valid"`;
- invalid target renders `data-cross-track-drop="invalid"`;
- no target renders no drop indicator;
- existing track controls and toolbar markup remain unchanged.

- [ ] **Step 2: Run focused RED**

Run: `pnpm --filter @haios/desktop test -- cross-track-timeline.test.ts`
Expected: FAIL because the drop-state surface does not exist.

- [ ] **Step 3: Extend drag capture**

Change move-mode drag state to capture at mouse-down:

```ts
{
  mode: "move";
  startX: number;
  startY: number;
  anchorClipId: string;
  startVals: Record<string, number>;
  sourceTrackIds: Record<string, string>;
}
```

Trim modes may keep only the fields they need via a discriminated union; do not force vertical state into trim/ripple logic.

- [ ] **Step 4: Resolve destination from actual rendered track rectangles**

During `onMouseMove`, collect `.timeline-inner > .track` elements and build:

```ts
const rects = Array.from(inner.querySelectorAll<HTMLElement>(":scope > .track")).map((el) => {
  const rect = el.getBoundingClientRect();
  return { trackId: el.dataset.trackId!, top: rect.top, bottom: rect.bottom };
});
const targetTrackId = resolveTrackAtClientY(rects, ev.clientY);
```

Add `data-track-id={track.id}` to each `.track`; do not infer destination using CSS lane height arithmetic.
- [ ] **Step 5: Keep horizontal snapping independent from vertical destination**

Retain current `findMagneticSnap` logic verbatim for `deltaSec`. Vertical target resolution runs alongside it. `ev.altKey` disables only snap candidates; target/kind/lock validation still runs.

Use the pure planner during preview only to classify the target as valid/invalid. Planner failures affect runtime styling, not Project state.

- [ ] **Step 6: Commit the drop on mouse-up**

Rules:
- if neither time nor track changed meaningfully, issue no command;
- one selected clip: `moveSelected(originalStart + delta, targetTrackIdIfChanged)`;
- multiple selected clips: `commitGroupMove(delta, anchorClipId, targetTrackIdIfChanged)`;
- preserve selection and primary clip;
- store updates `selectedTrackId` only after success;
- clear runtime preview/snap/drop state after either success or rejection.

- [ ] **Step 7: Add advisory styling only**

Add minimal classes such as `.track.cross-track-drop-valid` and `.track.cross-track-drop-invalid`. Do not hide locked tracks, alter track geometry, or encode authority in CSS.

- [ ] **Step 8: Run focused GREEN + geometry regressions**

Run:
- `pnpm --filter @haios/desktop test -- cross-track-timeline.test.ts cross-track-store.test.ts cross-track-move.test.ts`
- `pnpm --filter @haios/desktop test -- marquee-selection.test.ts ripple-workflow.test.ts transport-navigation.test.ts`
- `pnpm --filter @haios/desktop typecheck`
Expected: PASS.

- [ ] **Step 9: Commit Task 4 exact scope**

```bash
git add apps/desktop/src/components/Timeline.tsx apps/desktop/src/styles.css apps/desktop/tests/cross-track-timeline.test.ts
git diff --cached --check
git commit -m "feat(video-studio): add cross-track drag gestures"
```

### Task 5: Real-Tauri Pointer Acceptance

**Files:**
- Create: `apps/desktop/e2e/run-p5-cross-track-editorial-mobility.mjs`
- Modify test-only E2E fixture/bootstrap only if required; production `main.tsx` must remain untouched.
**Interfaces:**
- Uses raw W3C WebDriver pointer actions against rendered `.clip` and `.track-lane` rectangles.
- Setup may load a deterministic Project v2 through the existing E2E-only `haios-e2e-load-project` event; the movement itself must be a pointer gesture, not a store call.

- [ ] **Step 1: Build a deterministic v2 fixture in the runner**

Fixture topology:
- video tracks `v1`, `v2`, `v3` with clips on `v1` and `v2`;
- audio tracks `a1`, `a2` with one audio clip;
- one locked compatible destination;
- media assets already valid for Preview/Render.

- [ ] **Step 2: Add a reusable pointer drag helper**

Use WebDriver actions with element-origin or viewport coordinates derived from `getBoundingClientRect()`:

```js
await wd("POST", `/session/${sessionId}/actions`, { actions: [{
  type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, x: from.x, y: from.y, origin: "viewport" },
    { type: "pointerDown", button: 0 },
    { type: "pointerMove", duration: 250, x: to.x, y: to.y, origin: "viewport" },
    { type: "pointerUp", button: 0 },
  ],
}] });
```

- [ ] **Step 3: Assert real-GUI gates**

Emit and verify:
- `VIDEO_CROSS_TRACK_POINTER_DROP=PASS`
- `AUDIO_CROSS_TRACK_POINTER_DROP=PASS`
- `WRONG_KIND_POINTER_DROP_REJECTED=PASS`
- `LOCKED_DESTINATION_POINTER_DROP_REJECTED=PASS`
- `SNAP_DURING_CROSS_TRACK_DRAG=PASS`
- `MULTI_SELECTION_CROSS_TRACK_ATOMIC=PASS`
- `CROSS_TRACK_UNDO_REDO=PASS`
- `SELECTION_TARGET_CONTINUITY=PASS`
- `REAL_TAURI_POINTER_GESTURE=PASS`
- [ ] **Step 4: Build fresh E2E Tauri binary and run pointer harness**

Run from `apps/desktop`:
- `pnpm exec tauri build --debug` only if the existing E2E workflow explicitly uses debug; otherwise use the established release E2E configuration from current harness practice.
- Start `tauri-driver` on `127.0.0.1:4444` if not already running.
- `node e2e/run-p5-cross-track-editorial-mobility.mjs`

Expected: all nine gates PASS with exit code 0.

- [ ] **Step 5: Re-run legacy pointer/geometry lanes on the same binary**

Run:
- `node e2e/run-r2.1-webdriver.mjs`
- `node e2e/run-r2.14-ripple-workflow.mjs`
- `node e2e/run-r2.14b-gesture-transactions.mjs`
- `node e2e/run-r2.14c-marquee-selection.mjs`
- `node e2e/run-r2.14d-insert-overwrite.mjs`
- `node e2e/run-r2.14e-magnetic-snapping.mjs`
- `node e2e/run-r2.14f-transport-navigation.mjs`
Expected: PASS on one fresh binary; classify any failure before changing production code.

- [ ] **Step 6: Commit Task 5 exact scope**

```bash
git add apps/desktop/e2e/run-p5-cross-track-editorial-mobility.mjs
git diff --cached --check
git commit -m "test(video-studio): qualify cross-track pointer editing"
```

### Task 6: Cross-Runtime Save/Reopen and Preview≈Export Qualification

**Files:**
- Create: `apps/desktop/e2e/run-p5-cross-track-qualification.mjs`
- Reuse: production `hvs_render`, project save/open commands, P4.6 E2E-only project loader.

**Interfaces:**
- Input is one Project v2 fixture before movement.
- Movement is executed by the real GUI pointer harness or by replaying the saved result produced by Task 5; do not synthesize a different topology for export assertions.
- Output proves destination membership survives save/reopen and drives Preview/Render canonical composition.
- [ ] **Step 1: Add qualification assertions**

The runner must prove:
- moved clip is absent from original track and present once in destination;
- moved clip's persisted `trackId` equals the destination ID;
- save → reopen preserves membership/time exactly;
- Preview renders the moved clip at the destination layer/z-order;
- production `hvs_render` output reflects that same destination semantics;
- audio cross-track movement contributes through the destination audio track without duplication.

Emit:
- `SAVE_REOPEN_AFTER_MOVE=PASS`
- `PREVIEW_AFTER_MOVE=PASS`
- `EXPORT_AFTER_MOVE=PASS`
- `PREVIEW_EXPORT_AFTER_MOVE_PARITY=PASS`

- [ ] **Step 2: Run qualification on a fresh E2E binary**

Run:
- `node e2e/run-p5-cross-track-qualification.mjs`
- `node e2e/run-p4.6-phase4-qualification.mjs`
- `node e2e/run-p4.4-multitrack-render.mjs`
- `node e2e/run-r2.12-project-lifecycle.mjs`
Expected: Phase 5 gates PASS and Phase 4 parity/lifecycle gates remain PASS.

- [ ] **Step 3: Commit Task 6 exact scope**

```bash
git add apps/desktop/e2e/run-p5-cross-track-qualification.mjs
git diff --cached --check
git commit -m "test(video-studio): prove cross-track runtime parity"
```

### Task 7: Full Regression and Production Release Qualification

**Files:**
- No production changes unless a regression identifies a real defect.
- Modify only the exact stale harness if a failure is proven to be test-contract drift.

- [ ] **Step 1: Run fresh TypeScript/Vitest matrix**

Run: `pnpm -r test`
Expected: every workspace PASS; record exact per-package counts and total count.

- [ ] **Step 2: Run root typecheck**

Run: `pnpm typecheck`
Expected: PASS.

- [ ] **Step 3: Run Rust regression**

Run from `apps/desktop/src-tauri`: `cargo test`
Expected: all Rust tests PASS with the current count.
- [ ] **Step 4: Run full real-GUI/render regression matrix**

Run fresh E2E binary lanes covering:
- P5 pointer + P5 qualification;
- P4.6 Phase 4 parity;
- R2.12 project lifecycle;
- R2.13 render lifecycle;
- R2.1 and R2.14 through R2.14F editing/gesture/navigation;
- R2.8/R2.9/R2.10/R2.11 render fidelity lanes.

Expected: no regression blocker. Any failure must be classified as product defect versus stale harness before remediation.

- [ ] **Step 5: Build fresh production frontend/Tauri/MSI**

Run from `apps/desktop`: `pnpm tauri build`
Expected: production frontend, Rust release, and MSI bundling exit 0.

Record EXE/MSI path, timestamp, byte size, and SHA-256.

- [ ] **Step 6: Audit production hooks**

Scan production `dist/` and `target/release/haios-video-studio.exe` for E2E-only fixture/event marker strings.
Expected: `PRODUCTION_EXE_E2E_MARKERS=0` and `PRODUCTION_DIST_E2E_MARKERS=0`.

### Task 8: Independent Review, Checkpoint, and Final Seal

**Files:**
- Modify: `integrations/video-studio/CHECKPOINT.md`
- No other file may change during the final seal except reviewer remediation explicitly justified by a finding.
- [ ] **Step 1: Run independent read-only review**

Review exact Phase 5 range plus directly necessary Phase 4 authority. Reviewer must not modify files or run destructive git commands.

Required terminal format:

```text
CRITICAL_COUNT=<n>
IMPORTANT_COUNT=<n>
BLOCKERS=<none or concise>
```

Proceed only when `CRITICAL_COUNT=0`, `IMPORTANT_COUNT=0`, and `BLOCKERS=none`. If not zero, return to TDD remediation, rerun affected focused/broad qualification, and re-review current bytes.

- [ ] **Step 2: Append fresh Phase 5 evidence to checkpoint**

Record all terminal gates from the approved spec, exact test counts, real-GUI results, production artifact hashes, reviewer result, rollback baseline, implementation commit SHAs, and `BLOCKERS=none`.

- [ ] **Step 3: Remove Phase 5 temporary helpers only**

Delete only `.tmp_p5_*` files created by this implementation. Do not clean unrelated untracked files.

- [ ] **Step 4: Exact-stage checkpoint seal**

Run `git diff --check`, secret-pattern scan, temp/diagnostic scan, and exact allowlist verification. Stage only `integrations/video-studio/CHECKPOINT.md` for the final seal commit.

- [ ] **Step 5: Commit final Phase 5 seal**

```bash
git add integrations/video-studio/CHECKPOINT.md
git diff --cached --check
git commit -m "release(video-studio): seal cross-track editorial mobility"
```
- [ ] **Step 6: Build production artifacts again from the final seal commit**

Run `pnpm tauri build` after the seal commit so the final EXE/MSI are provably built from the repository terminal state, not only the pre-seal implementation head.

Re-record final EXE/MSI SHA-256 and confirm production E2E markers remain zero.

- [ ] **Step 7: Push normally and verify remote identity**

```bash
git push origin main
```

Then verify:

```text
HEAD_SHA == origin/main SHA == git ls-remote origin refs/heads/main SHA
REMOTE_EXACT_SHA=PASS
```

Do not force-push.

- [ ] **Step 8: Run post-seal production smoke**

Run the production EXE through P5 cross-track qualification plus R2.12 lifecycle and P4.4/P4.6 composition smoke where applicable.
Expected: runtime PASS from final production bytes.

## Terminal Definition of Done

The feature is closed only when every spec gate is fresh: single video/audio cross-track moves; missing/wrong-kind/source-lock/destination-lock fail-closed; exact undo/redo; atomic same-kind group movement; invalid batch zero mutation; snap during vertical drag; selected-track continuity; Preview/Export/save-reopen parity; real Tauri pointer acceptance; full TypeScript, typecheck, Rust, GUI/render regression; production Tauri/MSI; E2E marker count zero; independent review 0/0; exact-scope push; remote exact SHA.

## Rollback Boundaries

1. `docs(video-studio): specify cross-track editorial mobility` — approved design (`773e57c28d28f946b972da168b9889bf2fbfaf1b`).
2. Task 1 — command authority + tracked dist.
3. Task 2/3 — pure planner + store transaction authority.
4. Task 4 — Timeline pointer integration.
5. Task 5/6 — real-GUI and cross-runtime qualification harnesses.
6. Task 8 — final checkpoint seal.

At no point may implementation rewrite or squash the sealed Phase 4 history.
## Self-Review Coverage Matrix

The following exact spec gates are mandatory evidence names, not aliases:

- `SINGLE_VIDEO_CROSS_TRACK_MOVE=PASS` — Task 1 command test + Task 5 pointer test.
- `SINGLE_AUDIO_CROSS_TRACK_MOVE=PASS` — Task 1 command test + Task 5 pointer test.
- `WRONG_KIND_TARGET_FAIL_CLOSED=PASS` — Task 1 command test + Task 5 invalid pointer drop.
- `SOURCE_LOCKED_FAIL_CLOSED=PASS` — Task 1 command test.
- `DESTINATION_LOCKED_FAIL_CLOSED=PASS` — Task 1 command test + Task 5 locked pointer drop.
- `CROSS_TRACK_UNDO_EXACT=PASS` — Task 1 exact inverse + Task 5 one-step undo.
- `CROSS_TRACK_REDO_EXACT=PASS` — Task 1 redo + Task 5 one-step redo.
- `MULTI_CLIP_CROSS_TRACK_ATOMIC=PASS` — Task 3 batch test + Task 5 multi-selection gesture.
- `MIXED_VALID_INVALID_BATCH_ZERO_MUTATION=PASS` — Task 3 adversarial batch where one mapped destination is valid and another is locked/out-of-range; assert Project and undo history are unchanged.
- `SNAP_DURING_CROSS_TRACK_DRAG=PASS` — Task 4 independent snap calculation + Task 5 pointer proof.
- `SELECTED_TRACK_AFTER_DROP=PASS` — Task 3 success-only currentization + Task 5 DOM target assertion.
- `PREVIEW_AFTER_MOVE=PASS` — Task 6 destination-layer preview assertion.
- `EXPORT_AFTER_MOVE=PASS` — Task 6 production `hvs_render` assertion.
- `SAVE_REOPEN_AFTER_MOVE=PASS` — Task 6 exact Project v2 roundtrip.
- `REAL_TAURI_POINTER_GESTURE=PASS` — Task 5 raw WebDriver pointer actions.

Additional terminal gates are Task 7/8: full TypeScript/Vitest, root typecheck, Rust, production frontend/Tauri/MSI, production E2E marker count zero, independent review `0 Critical / 0 Important`, exact-scope push, and remote exact SHA.

Type/signature review result:
- `MOVE_CLIP` payload is consistently `{ clipId, newStart, targetTrackId? }` across Tasks 1-4.
- planner output feeds store batch payloads without translation aliases.
- selected-track currentization is store-owned and success-only.
- Project v2/Preview/Render contracts remain unchanged.
