import { cn } from "@/lib/utils";
import type { MascotMood } from "@/lib/types";
import type { MascotView } from "@/lib/utils";

// Per-mood visual tokens for Orbit. All CSS — no 3D libraries, no remote assets.
const MOOD_STYLES: Record<
  MascotMood,
  { glow: string; body: string; ring: string; label: string; dot: string }
> = {
  idle: {
    glow: "bg-status-idle",
    body: "from-slate-500/70 to-slate-800",
    ring: "border-status-idle/40",
    label: "Idle",
    dot: "bg-status-idle",
  },
  working: {
    glow: "bg-status-working",
    body: "from-amber-400/80 to-amber-700",
    ring: "border-status-working/50",
    label: "Working",
    dot: "bg-status-working",
  },
  blocked: {
    glow: "bg-status-blocked",
    body: "from-rose-400/80 to-rose-700",
    ring: "border-status-blocked/50",
    label: "Blocked",
    dot: "bg-status-blocked",
  },
  approved: {
    glow: "bg-status-approved",
    body: "from-emerald-400/80 to-emerald-700",
    ring: "border-status-approved/50",
    label: "All clear",
    dot: "bg-status-approved",
  },
  review: {
    glow: "bg-status-review",
    body: "from-violet-400/80 to-violet-700",
    ring: "border-status-review/50",
    label: "Thinking",
    dot: "bg-status-review",
  },
};

function OrbitMascot({ mood }: { mood: MascotMood }) {
  const s = MOOD_STYLES[mood];
  return (
    <div className="relative flex h-28 w-28 items-center justify-center">
      {/* Soft mood glow */}
      <div
        className={cn(
          "orbit-glow absolute h-24 w-24 rounded-full blur-2xl opacity-60",
          s.glow,
        )}
        aria-hidden
      />
      {/* Floating body */}
      <div className="orbit-float relative">
        {/* Rotating accent ring */}
        <div
          className={cn(
            "orbit-ring absolute -inset-2 rounded-full border-2 border-dashed",
            s.ring,
          )}
          aria-hidden
        />
        {/* Orb body with layered gradient for a 3D feel */}
        <div
          className={cn(
            "relative flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br shadow-[inset_-6px_-8px_16px_rgba(0,0,0,0.45),inset_4px_6px_12px_rgba(255,255,255,0.15)]",
            s.body,
          )}
        >
          {/* Specular highlight */}
          <div
            className="absolute left-4 top-3 h-4 w-4 rounded-full bg-white/40 blur-[2px]"
            aria-hidden
          />
          {/* Eyes */}
          <div className="flex gap-2.5">
            <span className="orbit-eye block h-3.5 w-2 rounded-full bg-slate-900/85" />
            <span className="orbit-eye block h-3.5 w-2 rounded-full bg-slate-900/85" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function MascotAssistant({ view }: { view: MascotView }) {
  const s = MOOD_STYLES[view.mood];
  return (
    <section
      aria-label="Orbit assistant"
      className="rounded-card border border-border bg-gradient-to-b from-surface-2 to-surface p-5 shadow-lg shadow-black/20"
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-ink">
            Orbit
          </h2>
          <p className="text-xs text-ink-faint">Your control-center assistant</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-xs font-medium text-ink-muted ring-1 ring-inset ring-border">
          <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} aria-hidden />
          {s.label}
        </span>
      </div>

      <div className="mt-2 flex justify-center">
        <OrbitMascot mood={view.mood} />
      </div>

      <p className="mt-1 text-center text-sm leading-relaxed text-ink">
        {view.message}
      </p>

      <div className="mt-4 space-y-3">
        <div className="rounded-xl border border-border-soft bg-surface p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Recommended next action
          </p>
          <p className="mt-1 text-sm text-ink">{view.nextAction}</p>
        </div>
        <div className="rounded-xl border border-border-soft bg-surface p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Selected task
          </p>
          <p className="mt-1 text-sm text-ink-muted">{view.taskSummary}</p>
        </div>
      </div>
    </section>
  );
}
