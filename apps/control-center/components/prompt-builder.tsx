"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { AGENTS } from "@/lib/mock-data";
import type { AgentId, Task } from "@/lib/types";

const TEMPLATES: { id: string; label: string; body: string }[] = [
  {
    id: "build",
    label: "Build slice",
    body: "Implement the selected task slice with tests and a typed contract.",
  },
  {
    id: "verify",
    label: "Verify",
    body: "Independently verify the change set and return a PASS/FAIL verdict.",
  },
  {
    id: "audit",
    label: "Audit",
    body: "Audit repo health and workflow files; report any blocking gaps.",
  },
];

export function PromptBuilder({
  selectedTask,
  targetAgentId,
  onChangeTargetAgent,
}: {
  selectedTask: Task | undefined;
  targetAgentId: AgentId;
  onChangeTargetAgent: (id: AgentId) => void;
}) {
  const [templateId, setTemplateId] = useState<string>(TEMPLATES[0].id);
  const template =
    TEMPLATES.find((t) => t.id === templateId) ?? TEMPLATES[0];

  const contextLine = selectedTask
    ? `Context: ${selectedTask.code} — ${selectedTask.title} (${selectedTask.stage}).`
    : "Context: no task selected.";

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Prompt Builder</h2>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-faint ring-1 ring-inset ring-border">
          Prototype · nothing is sent
        </span>
      </div>

      <div className="mt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Target agent
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {AGENTS.map((agent) => {
            const active = agent.id === targetAgentId;
            return (
              <button
                key={agent.id}
                type="button"
                onClick={() => onChangeTargetAgent(agent.id)}
                aria-pressed={active}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left transition-colors",
                  active
                    ? "border-accent/60 bg-accent/10 ring-1 ring-inset ring-accent/30"
                    : "border-border hover:bg-surface-2",
                )}
              >
                <span className="block text-xs font-medium text-ink">
                  {agent.name}
                </span>
                <span className="block text-[11px] text-ink-faint">
                  {agent.role}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Template
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {TEMPLATES.map((t) => {
            const active = t.id === templateId;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTemplateId(t.id)}
                aria-pressed={active}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  active
                    ? "bg-accent/15 text-ink ring-1 ring-inset ring-accent/30"
                    : "bg-surface-2 text-ink-muted hover:text-ink",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <label className="mt-4 block">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Prompt preview
        </span>
        <textarea
          readOnly
          rows={4}
          value={`${contextLine}\n\n${template.body}`}
          className="mt-2 w-full resize-none rounded-xl border border-border-soft bg-surface-2 p-3 text-sm text-ink-muted focus:border-accent/50 focus:outline-none"
        />
      </label>

      <div className="mt-3 flex items-center justify-between">
        <p className="text-[11px] text-ink-faint">
          Dispatch is disabled in this prototype.
        </p>
        <button
          type="button"
          disabled
          className="cursor-not-allowed rounded-lg bg-accent/40 px-4 py-2 text-sm font-medium text-white/80 opacity-60"
        >
          Send to agent
        </button>
      </div>
    </section>
  );
}
