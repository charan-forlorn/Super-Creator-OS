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
    rippleDeleteSelected,
    splitSelected,
    duplicateSelected,
    commitGroupMove,
    selectedClipIds,
    selectedClipId,
    playheadSec,
    stepPlayhead,
    jumpPlayhead,
    toggleTransport,
    setTransportRate,
    selectAllClips,
    clearClipSelection,
  } = useStudio();

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      const target = ev.target as HTMLElement;
      const inputType = target?.tagName === "INPUT" ? (target as HTMLInputElement).type : "";
      const textEditingTarget = target && (
        target.tagName === "TEXTAREA" ||
        target.isContentEditable ||
        (target.tagName === "INPUT" && !["checkbox", "radio", "button", "submit", "reset"].includes(inputType))
      );
      if (textEditingTarget) return;

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
      // Arrow keys nudge clips when selected; otherwise navigate the playhead.
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
        ev.preventDefault();
        const direction = ev.key === "ArrowLeft" ? -1 : 1;
        if (selectedClipIds.length) {
          const step = ev.shiftKey ? 0.1 : 0.5;
          commitGroupMove(direction * step);
        } else stepPlayhead(direction, ev.shiftKey);
        return;
      }
      // Delete / Backspace. Shift+Delete is production ripple delete.
      if (ev.key === "Delete" || ev.key === "Backspace") {
        if (selectedClipIds.length) {
          ev.preventDefault();
          if (ev.shiftKey) rippleDeleteSelected();
          else deleteSelected();
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
      if (ev.key === "Home") { ev.preventDefault(); jumpPlayhead("start"); return; }
      if (ev.key === "End") { ev.preventDefault(); jumpPlayhead("end"); return; }
      if (!mod && (ev.key === "j" || ev.key === "J")) { ev.preventDefault(); setTransportRate(-1); return; }
      if (!mod && (ev.key === "k" || ev.key === "K")) { ev.preventDefault(); setTransportRate(0); return; }
      if (!mod && (ev.key === "l" || ev.key === "L")) { ev.preventDefault(); setTransportRate(1); return; }
      if (ev.code === "Space") { ev.preventDefault(); toggleTransport(); return; }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    undo,
    redo,
    deleteSelected,
    rippleDeleteSelected,
    splitSelected,
    duplicateSelected,
    commitGroupMove,
    selectedClipIds,
    selectedClipId,
    playheadSec,
    stepPlayhead,
    jumpPlayhead,
    toggleTransport,
    setTransportRate,
    selectAllClips,
    clearClipSelection,
  ]);
}
