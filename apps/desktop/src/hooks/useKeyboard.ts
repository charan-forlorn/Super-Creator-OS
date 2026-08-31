import { useEffect } from "react";
import { useStudio } from "../store";

/**
 * Global editor keyboard shortcuts. All edits route through the CommandBus.
 * R2.1: multi-selection aware — delete/split/duplicate act on the full selection
 * and collapse to one undoable unit; arrow keys nudge the selection.
 */
export function useKeyboard() {
  const {
    undo,
    redo,
    deleteSelected,
    splitSelected,
    duplicateSelected,
    commitGroupMove,
    selectedClipIds,
    selectedClipId,
    playheadSec,
    selectAllClips,
    clearClipSelection,
  } = useStudio();

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      const target = ev.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

      const mod = ev.ctrlKey || ev.metaKey;

      // Undo / redo
      if (mod && (ev.key === "z" || ev.key === "Z")) {
        ev.preventDefault();
        if (ev.shiftKey) redo();
        else undo();
        return;
      }
      if (mod && (ev.key === "y" || ev.key === "Y")) {
        ev.preventDefault();
        redo();
        return;
      }
      // Select all clips
      if (mod && (ev.key === "a" || ev.key === "A")) {
        ev.preventDefault();
        selectAllClips();
        return;
      }
      // Duplicate selection
      if (mod && (ev.key === "d" || ev.key === "D")) {
        if (selectedClipIds.length) {
          ev.preventDefault();
          duplicateSelected();
        }
        return;
      }
      // Escape clears selection
      if (ev.key === "Escape") {
        clearClipSelection();
        return;
      }
      // Nudge selection left/right by 0.5s (hold Shift = 0.1s fine)
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
        if (selectedClipIds.length) {
          ev.preventDefault();
          const step = ev.shiftKey ? 0.1 : 0.5;
          commitGroupMove(ev.key === "ArrowLeft" ? -step : step);
        }
        return;
      }
      // Delete / Backspace
      if (ev.key === "Delete" || ev.key === "Backspace") {
        if (selectedClipIds.length) {
          ev.preventDefault();
          deleteSelected();
        }
        return;
      }
      // Split selected at playhead (S)
      if (ev.key === "s" || ev.key === "S") {
        if (selectedClipIds.length) {
          ev.preventDefault();
          // splitSelected resolves each clip's local playhead offset internally
          splitSelected(undefined);
        }
        return;
      }
      // Space: reserved for play toggle (handled by Preview); no-op here to avoid scroll.
      if (ev.code === "Space") {
        ev.preventDefault();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    undo,
    redo,
    deleteSelected,
    splitSelected,
    duplicateSelected,
    commitGroupMove,
    selectedClipIds,
    selectedClipId,
    playheadSec,
    selectAllClips,
    clearClipSelection,
  ]);
}
