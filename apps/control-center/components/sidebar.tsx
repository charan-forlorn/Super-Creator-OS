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
  { id: "live", label: "Live Updates", icon: "◉", hint: "Simulated feed" },
  { id: "command-bridge", label: "Command Bridge", icon: "⌘", hint: "Stage 5.1 mock" },
  { id: "ai-work-sessions", label: "AI Work Sessions", icon: "◈", hint: "Stage 5.2 mock" },
  { id: "agent-adapters", label: "Agent Adapters", icon: "⇄", hint: "Stage 5.3 mock" },
  { id: "prompt-packets", label: "Prompt Packets", icon: "⇉", hint: "Stage 5.4 mock" },
  { id: "packet-review", label: "Packet Review", icon: "PR", hint: "Stage 5.5 mock" },
  { id: "workflow-router", label: "Cross-Agent Router", icon: "⇄", hint: "Stage 5.6 mock" },
  { id: "result-intake", label: "Result Intake", icon: "⇊", hint: "Stage 5.7 mock" },
  { id: "git-approval", label: "Commit/Push Gate", icon: "⇑", hint: "Stage 5.8 mock" },
  { id: "operator-execution", label: "Execution Console", icon: "▶", hint: "Stage 5.9 mock" },
  { id: "stage5-certification", label: "Stage 5 Certification", icon: "✓", hint: "Stage 5.10 mock" },
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
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface/60 lg:flex">
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

/**
 * Compact horizontal navigation shown below `lg`, where the vertical sidebar is hidden.
 * Stateless: reuses NAV_SECTIONS and the same activeSection/onSelect props as Sidebar.
 * No local state, no drawer, no routing.
 */
export function TopNav({
  activeSection,
  onSelect,
}: {
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav
      aria-label="Sections"
      className="flex gap-1.5 overflow-x-auto border-b border-border bg-surface/50 px-4 py-2"
    >
      {NAV_SECTIONS.map((section) => {
        const active = section.id === activeSection;
        return (
          <button
            key={section.id}
            type="button"
            onClick={() => onSelect(section.id)}
            aria-current={active ? "true" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              active
                ? "bg-accent/15 text-ink ring-1 ring-inset ring-accent/30"
                : "text-ink-muted hover:bg-surface-2 hover:text-ink",
            )}
          >
            <span
              className={cn(active ? "text-accent" : "text-ink-faint")}
              aria-hidden
            >
              {section.icon}
            </span>
            {section.label}
          </button>
        );
      })}
    </nav>
  );
}
