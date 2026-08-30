import { useEffect } from "react";
import { useStudio } from "../store";

/** Global editor keyboard shortcuts. All edits route through the CommandBus. */
export function useKeyboard() {
  const { undo, redo, deleteSelected, splitSelected, selectedClipId, playheadSec } = useStudio();
  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      const target = ev.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (ev.code === "Space") {
        ev.preventDefault();
        // toggle play handled by Preview; here we just no-op to avoid scroll
        return;
      }
      const mod = ev.ctrlKey || ev.metaKey;
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
      if (ev.key === "Delete" || ev.key === "Backspace") {
        if (selectedClipId) {
          ev.preventDefault();
          deleteSelected();
        }
        return;
      }
      if (ev.key === "s" || ev.key === "S") {
        if (selectedClipId) {
          ev.preventDefault();
          // split at playhead when valid (t between 0 and duration)
          const clip = useStudio.getState().project.tracks.flatMap((t) => t.clips).find((c) => c.id === selectedClipId);
          if (clip) {
            const local = playheadSec - clip.start;
            if (local > 0 && local < clip.duration) splitSelected(local);
          }
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, deleteSelected, splitSelected, selectedClipId, playheadSec]);
}
