# Phase 5 — Cross-Track Editorial Mobility Design

Status: DESIGN APPROVED / WRITTEN SPEC PENDING USER REVIEW
Date: 2026-09-01
Safe baseline: `001a4e9910b16dc256d09bbf70b3b733f228a861`
Authority: Project v2 + CommandBus + CompositionPlan + Preview≈Export

## 1. Purpose

Phase 4 established true multi-track composition, but timeline clip movement is still horizontal-only because `clip.move` accepts `clipId` and `newStart` without a destination track.

Phase 5 closes that workflow gap by making compatible cross-track clip movement a first-class, undoable CommandBus operation while preserving every Phase 4 invariant.

The user outcome is a practical editor workflow where clips can be dragged between compatible tracks without bypassing lock authority, atomic history, snapping, Preview≈Export, or persisted Project truth.

## 2. Scope

This slice adds:

- single video clip movement between video tracks;
- single audio clip movement between audio tracks;
- atomic same-kind multi-selection cross-track movement;
- destination-track resolution during timeline drag;
- compatible-track drop preview and invalid-drop feedback;
- exact undo/redo of both time and track membership;
- selected target-track currentization after a successful cross-track drop;
- real-Tauri and Preview/Export qualification of the resulting Project v2 state.

## 3. Explicit Non-Goals

This slice does not add:

- Project schema v3 or any new persisted field;
- new render authority or FFmpeg topology;
- track Solo, track gain, meters, keyframes, markers, compound clips, slip/slide/roll editing, or speed ramps;
- cross-kind movement such as video→audio or audio→video;
- vertical movement of mixed video+audio selections;
- automatic track creation during drag;
- changes to caption-track movement;
- changes to track reorder gestures.

Those remain separate architecture slices.

## 4. Core Command Contract

`MOVE_CLIP` remains the canonical movement command and is extended, not replaced:

```ts
{
  clipId: string;
  newStart: number;
  targetTrackId?: string;
}
```

Omitting `targetTrackId` preserves current same-track behavior exactly.

Providing `targetTrackId` requests an atomic time + membership move.

## 5. CommandBus Validation and Failure Semantics

Before mutation, `MOVE_CLIP` must resolve the source clip and source track and then validate the destination.

Required checks:

1. source clip exists;
2. source track exists;
3. `newStart >= 0` through schema validation;
4. source track is unlocked;
5. if `targetTrackId` is supplied, the target track exists;
6. target track kind equals source track kind;
7. destination track is unlocked.

Cross-track failures are fail-closed and produce zero Project mutation and zero history mutation.

Stable errors:

- `TRACK_LOCKED: <source-or-target-id>` for locked source or destination;
- `CLIP_MOVE_TARGET_TRACK_NOT_FOUND: <id>` for missing destination;
- `CLIP_MOVE_TARGET_TRACK_KIND_MISMATCH: <id>` for incompatible destination.

The inverse command captures the original `trackId` and original `start`, so one undo restores both exactly. Redo reapplies the forward destination and time.

## 6. Persisted-State Invariants

A moved clip remains a single persisted clip object. Its `trackId` must always equal the containing track ID after every forward, undo, and redo operation.

Cross-track movement must not duplicate or orphan clips. The clip is removed from exactly one source track and inserted into exactly one destination track.

## 7. Multi-Selection Transaction Model

Horizontal group movement remains supported for any current valid selection.

Vertical cross-track movement is intentionally narrower:

- every selected clip must share the same track kind as the dragged anchor clip;
- mixed video+audio selections may still move horizontally, but a vertical drop is rejected atomically;
- selected clips may originate from more than one track of that same kind.

For a same-kind group move, compatible tracks are ordered by their canonical Project track order. The dragged anchor establishes a compatible-track index delta:

`destinationIndex(anchor) - sourceIndex(anchor) = laneDelta`

Every selected clip maps its source compatible-track index through the same `laneDelta`. This preserves relative same-kind track spacing.

If any mapped destination is missing, wrong-kind, or locked, the entire group move is rejected with zero mutation.

The existing `CommandBus.batch()` remains transaction authority because it validates before assignment, applies against accumulated state, records one undo entry, and fails closed on any sub-command failure.

## 8. Timeline Gesture Model

`onClipMouseDown` captures:

- dragged anchor clip ID;
- selected clip IDs;
- original starts;
- original source track IDs;
- pointer origin.

Horizontal movement continues to calculate the time delta and magnetic snap exactly as today.

Vertical destination resolution uses the rendered track lanes already present in Timeline; it does not infer track IDs from arithmetic on CSS heights. The pointer position is resolved against actual `.track` / `.track-lane` DOM rectangles so future lane-height styling changes do not silently change movement authority.

During move preview:

- compatible unlocked destinations show a valid drop state;
- incompatible, missing mapping, or locked destinations show an invalid drop state;
- the horizontal snap guide remains active independently;
- Alt continues to bypass magnetic snapping only; it never bypasses lock or kind validation.

Trim, ripple-trim, marquee, ruler, track-control, and track-reorder gestures keep their existing authorities and do not participate in cross-track movement.

## 9. Commit Semantics

A mouse-up with no meaningful horizontal or vertical change performs no command and creates no history entry.

A successful single-clip drop dispatches one `MOVE_CLIP` with `newStart` and, only when track membership changes, `targetTrackId`.

A successful multi-selection drop dispatches one `CommandBus.batch()` containing deterministic `MOVE_CLIP` payloads for every selected clip. The batch order follows canonical selected-clip resolution, not DOM incidental ordering.

After a successful cross-track drop:

- clip selection is preserved;
- the primary selected clip remains primary;
- `selectedTrackId` becomes the primary clip's destination track;
- Project `updatedAt` changes through CommandBus authority;
- dirty state becomes true through the existing store synchronization path.

On rejected drop, selection and selected target track remain unchanged and `lastError` receives the command failure.

## 10. Preview and Export Impact

No new composition schema is introduced.

Because Project v2 remains canonical truth and both Preview and Rust export already derive composition from track membership, a successful move becomes visible to both runtimes through the existing pipeline:

`MOVE_CLIP → Project v2 → CompositionPlan / RenderCompositionPlan → Preview + Export`

This slice must not add preview-only or renderer-only track remapping.

Qualification must prove that a moved clip renders from the destination track with the same canonical z-order/audio semantics already sealed in Phase 4.

## 11. Compatibility Rules

Existing callers of `MOVE_CLIP` that send only `{ clipId, newStart }` must remain behaviorally unchanged.

Existing horizontal drag, keyboard nudge, ripple, trim, split, duplicate, insert/overwrite, snapping, transport, save/open, and render workflows remain regression authorities.

No persisted migration is required because `Clip.trackId` and Track membership already exist in Project v2.

## 12. Likely Implementation Surfaces

Expected production surfaces are deliberately small:

- `packages/command-system/src/commands.ts` and tracked dist;
- command-system acceptance tests;
- `apps/desktop/src/store.ts`;
- `apps/desktop/src/components/Timeline.tsx`;
- focused desktop tests and one real-Tauri cross-track runner;
- Phase 5 checkpoint evidence.

A new package or renderer subsystem is not justified by this slice.

## 13. TDD and Test Strategy

Implementation begins with failing CommandBus tests before production code changes.

Command-level RED→GREEN coverage must include:

- same-track move compatibility;
- single video cross-track move;
- single audio cross-track move;
- wrong-kind destination rejection;
- missing destination rejection;
- locked source rejection;
- locked destination rejection;
- exact cross-track undo/redo;
- clip containment and `clip.trackId` consistency.

Store/transaction coverage must then prove:

- same-kind group lane-delta mapping;
- one-history-entry batch semantics;
- mixed-kind vertical rejection;
- out-of-range mapped destination rejection;
- mixed valid/invalid batch zero mutation;
- selected target-track update only after success.

Timeline-focused tests cover destination resolution and preview state without using source-string assertions.

Real-Tauri qualification must exercise pointer movement across actual track lanes, not a store backdoor.

The real-GUI runner must prove:

- video→video pointer drop;
- audio→audio pointer drop;
- invalid video→audio drop rejection;
- locked destination rejection;
- horizontal snapping during a vertical move;
- multi-selection atomic cross-track move;
- one-step undo and redo;
- selection/target-track continuity.

Preview/export qualification then saves the moved Project v2, reopens it, renders it through production `hvs_render`, and verifies the destination-layer semantics.

## 14. Terminal Acceptance Gates

Phase 5 is not complete until all of the following are fresh and current:

- `SINGLE_VIDEO_CROSS_TRACK_MOVE=PASS`
- `SINGLE_AUDIO_CROSS_TRACK_MOVE=PASS`
- `WRONG_KIND_TARGET_FAIL_CLOSED=PASS`
- `SOURCE_LOCKED_FAIL_CLOSED=PASS`
- `DESTINATION_LOCKED_FAIL_CLOSED=PASS`
- `CROSS_TRACK_UNDO_EXACT=PASS`
- `CROSS_TRACK_REDO_EXACT=PASS`
- `MULTI_CLIP_CROSS_TRACK_ATOMIC=PASS`
- `MIXED_VALID_INVALID_BATCH_ZERO_MUTATION=PASS`
- `SNAP_DURING_CROSS_TRACK_DRAG=PASS`
- `SELECTED_TRACK_AFTER_DROP=PASS`
- `PREVIEW_AFTER_MOVE=PASS`
- `EXPORT_AFTER_MOVE=PASS`
- `PREVIEW_EXPORT_AFTER_MOVE_PARITY=PASS`
- `SAVE_REOPEN_AFTER_MOVE=PASS`
- `REAL_TAURI_POINTER_GESTURE=PASS`
- full TypeScript/Vitest regression PASS;
- root typecheck PASS;
- Rust regression PASS;
- production frontend/Tauri/MSI PASS;
- production E2E marker audit = 0;
- independent review `CRITICAL_COUNT=0`;
- independent review `IMPORTANT_COUNT=0`;
- exact-scope commit/push and remote exact SHA PASS.

## 15. Security and Failure Handling

Track lock is an authority boundary, not a UI hint. UI invalid-drop styling is advisory only; CommandBus must independently reject locked or incompatible destinations.

No file-system path, media source, or render command is changed by destination resolution. The operation changes only persisted Project membership and start time.

Malformed or stale UI payloads therefore fail at command schema/authority instead of creating partially valid Project state.

## 16. Rollback and Delivery Strategy

The Phase 4 seal `001a4e9910b16dc256d09bbf70b3b733f228a861` remains the rollback baseline.

Delivery should use isolated rollback boundaries:

1. command/store authority + tracked dist;
2. timeline gesture/UI integration;
3. cross-runtime qualification/remediation if required;
4. final Phase 5 seal.

Every commit stages only the exact allowlisted Phase 5 paths. Unrelated Control Center/SCOS dirty work must not be staged, reset, cleaned, or reformatted.
