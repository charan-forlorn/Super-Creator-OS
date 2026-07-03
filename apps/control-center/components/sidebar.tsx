"use client";

import { cn } from "@/lib/utils";

export interface NavSection {
  id: string;
  label: string;
  icon: string;
  hint: string;
}

export const NAV_SECTIONS: NavSection[] = [
  { id: "overview", label: "Overview", icon: "◎", hint: "Agents & stage" },
  { id: "board", label: "Task Board", icon: "▤", hint: "Kanban" },
  { id: "prompt", label: "Prompt Builder", icon: "✎", hint: "Dispatch work" },
  { id: "inbox", label: "Result Inbox", icon: "✔", hint: "PASS / FAIL" },
  { id: "merge", label: "Merge Queue", icon: "⑃", hint: "Review & merge" },
  { id: "timeline", label: "Timeline", icon: "≡", hint: "Recent activity" },
];

export function Sidebar({
  activeSection,
  onSelect,
}: {
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface/60">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/20 text-accent ring-1 ring-inset ring-accent/40">
          <span className="text-base font-bold">S</span>
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-ink">SCOS</p>
          <p className="text-[11px] text-ink-faint">Control Center</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV_SECTIONS.map((section) => {
          const active = section.id === activeSection;
          return (
            <button
              key={section.id}
              type="button"
              onClick={() => onSelect(section.id)}
              className={cn(
                "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors",
                active
                  ? "bg-accent/15 text-ink ring-1 ring-inset ring-accent/30"
                  : "text-ink-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <span
                className={cn(
                  "text-base",
                  active ? "text-accent" : "text-ink-faint",
                )}
                aria-hidden
              >
                {section.icon}
              </span>
              <span className="flex-1">
                <span className="block text-sm font-medium">{section.label}</span>
                <span className="block text-[11px] text-ink-faint">
                  {section.hint}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="border-t border-border px-5 py-4">
        <p className="text-[11px] leading-relaxed text-ink-faint">
          v0.1 prototype · local-first · no backend connected.
        </p>
      </div>
    </aside>
  );
}
