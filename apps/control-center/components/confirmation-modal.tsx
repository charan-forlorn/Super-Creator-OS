"use client";

import { useEffect, useRef } from "react";

export interface ConfirmationModalProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  /** When true the confirm action is disabled (e.g. bridge not ready). */
  disabled?: boolean;
  disabledReason?: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Accessible confirmation dialog.
 * - role="dialog" + aria-modal + labelled/describedby
 * - focus moved in on open, restored to trigger on close
 * - ESC and backdrop click CANCEL (never execute)
 * - the only execute path is the explicit confirm button
 * Hard rule: nothing fires on mount, timeout, focus loss, or backdrop click.
 */
export function ConfirmationModal({
  open,
  title,
  description,
  confirmLabel,
  disabled = false,
  disabledReason,
  pending = false,
  onConfirm,
  onCancel,
}: Readonly<ConfirmationModalProps>) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    lastTrigger.current = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === "Tab") {
        const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      lastTrigger.current?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        aria-describedby="confirm-modal-desc"
        className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-xl"
      >
        <h2 id="confirm-modal-title" className="text-sm font-semibold text-ink">
          {title}
        </h2>
        <p id="confirm-modal-desc" className="mt-2 text-xs text-ink-muted">
          {description}
        </p>
        {disabled && disabledReason ? (
          <p className="mt-3 rounded-lg border border-status-waiting/40 bg-status-waiting/10 p-2 text-xs text-status-waiting" role="status">
            {disabledReason}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            className="rounded-lg border border-status-failed/50 bg-status-failed/10 px-4 py-2 text-sm font-semibold text-status-failed disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled || pending}
            aria-disabled={disabled || pending}
            onClick={onConfirm}
          >
            {pending ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
